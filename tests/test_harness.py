"""The MAGE-repurposed optimizer harness, against the real equivalence gate.

The model is stubbed (deterministic canned rewrites of mul8); the GRADER is real
(Verilator locally). So these prove the scaffold's control flow — diversity pool,
equivalence gate, and the repair loop — wire correctly to the immutable grader.
PPA ranking (Yosys) is covered by the grader's own tests / the Modal floor.
"""

from __future__ import annotations

import shutil

import pytest

from cologic.designs import MUL8_BROKEN, MUL8_GOOD, mul8
from cologic.grader import EQUIV_BASE
from harness import HarnessConfig, optimize
from harness.optimizer import demo

pytestmark = pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")


def _stub_model_broken_then_good():
    """First rewrite is broken; every later call (more rewrites + repairs) is good."""
    state = {"n": 0}

    def model_fn(messages, *, temperature, max_tokens):
        state["n"] += 1
        return MUL8_BROKEN if state["n"] == 1 else MUL8_GOOD

    return model_fn


def test_harness_catches_and_repairs_broken_rewrite():
    res = optimize(
        mul8,
        model_fn=_stub_model_broken_then_good(),
        config=HarnessConfig(n_candidates=2, max_repair_rounds=1, keep_baseline=True),
    )
    # The gate rejected the broken rewrite...
    assert any(not c.equivalent for c in res.pool), res.pool
    # ...the debug agent ran on it...
    assert any("repair" in c.origin for c in res.pool), [c.origin for c in res.pool]
    # ...and the surviving best is provably equivalent.
    assert res.best.equivalent
    assert res.best.reward >= EQUIV_BASE
    assert res.n_equivalent >= 2  # baseline + at least one good rewrite


def test_harness_seeds_baseline_as_floor():
    """With keep_baseline, the reference is always in the pool as a reward floor."""
    res = optimize(
        mul8,
        model_fn=lambda *a, **k: MUL8_GOOD,
        config=HarnessConfig(n_candidates=1, keep_baseline=True),
    )
    assert any(c.origin == "baseline" for c in res.pool)
    assert res.best.equivalent


def test_offline_demo_runs():
    """Pure offline (stub model + stub grader) — no Verilator, no API key."""
    demo()
