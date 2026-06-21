"""Oracle validation for the serious benchmark: the REAL `tt_um_tpu` optimizer task.

These tests cover the *machinery* — does the equivalence + PPA gate behave correctly
on real, external, clocked RTL — NOT whether any particular optimization is good.
We deliberately ship no reference-optimal rewrite: the whole point of the benchmark
is that the tooling, not us, decides what counts as an improvement. So the only
hand-authored RTL here is a deliberately-BROKEN mutant, used to prove the gate
rejects a bad rewrite.

Tiers:
  * Verilator only (local/CI) -> the clocked equivalence gate: baseline self-grades
    equivalent; the broken-product mutant is caught.
  * Verilator + Yosys (Modal) -> the baseline's area is computable and the
    resource-sharing headroom (multiple un-shared MAC units) actually exists.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cologic.designs import TPU_MATMUL_BASELINE, TPU_MATMUL_BROKEN, tpu_matmul
from cologic.grader import EQUIV_BASE, NOT_EQUIVALENT_REWARD, grade
from cologic.grader.ppa import synth_cells, yosys_available

HAVE_VERILATOR = shutil.which("verilator") is not None
verilator_only = pytest.mark.skipif(not HAVE_VERILATOR, reason="verilator not installed")
needs_yosys = pytest.mark.skipif(
    not (HAVE_VERILATOR and yosys_available()),
    reason="PPA stage needs verilator + yosys (runs in the Modal image)",
)


@verilator_only
def test_real_tpu_baseline_self_grades_equivalent():
    """The external baseline must be equivalent to itself under the clocked TB, or
    it could never serve as the optimizer's oracle."""
    r = grade(TPU_MATMUL_BASELINE, tpu_matmul)
    assert r.info["equivalent"] is True
    assert r.info["eq_passed"] == r.info["eq_total"] > 0
    assert r.reward >= EQUIV_BASE


@verilator_only
def test_clocked_gate_catches_a_broken_rewrite():
    """A single wrong product (C11 uses b2 for b3) is wrong only when output_sel==3
    and b2 != b3 — rare, so this proves the clocked co-sim is what makes the reward
    unfakeable, not luck."""
    r = grade(TPU_MATMUL_BROKEN, tpu_matmul)
    assert r.info["equivalent"] is False
    assert r.info["compiled"] is True
    assert r.info["stage"] == "not_equivalent"
    assert 0 < r.info["eq_passed"] < r.info["eq_total"]  # passes most scenarios, fails some
    assert r.reward == NOT_EQUIVALENT_REWARD


@verilator_only
def test_broken_rewrite_differs_from_baseline():
    """Sanity: the mutant is actually a different circuit (guards against a no-op
    replace silently making the 'broken' case identical to the baseline)."""
    assert TPU_MATMUL_BROKEN != TPU_MATMUL_BASELINE


@needs_yosys
def test_baseline_area_is_computable_and_headroom_exists():
    """On Yosys, the baseline synthesizes and the recorded loop winner is smaller.

    Do not assert internal `$mul`/`$macc` names: newer Yosys versions summarize
    post-synth cells differently. The invariant that matters for the demo is the
    measured headroom after the same synth recipe.
    """
    area = synth_cells(TPU_MATMUL_BASELINE, tpu_matmul.top_module)
    optimized = synth_cells(
        Path("docs/tpu_matmul_optimization/after.v").read_text(encoding="utf-8"),
        tpu_matmul.top_module,
    )
    assert area.cells > optimized.cells > 0
    # And the graded baseline reports a real cell count via the PPA path.
    r = grade(TPU_MATMUL_BASELINE, tpu_matmul)
    assert r.info["stage"] == "graded"
    assert r.info["ref_cells"] == r.info["cand_cells"] > 0  # baseline vs itself
