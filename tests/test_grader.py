"""Floor proof: the equivalence gate catches a subtly-broken rewrite.

These run on Verilator alone (installed locally). The Yosys PPA stage is exercised
separately in the Modal image; here an equivalent design lands at EQUIV_BASE with
stage "equivalent_no_ppa" when yosys is absent, or "graded" when it is present.
"""

from __future__ import annotations

import pytest

from cologic.designs import MUL8_BASELINE, MUL8_BROKEN, MUL8_GOOD, mul8
from cologic.grader import EQUIV_BASE, EQUIV_FLOOR, NOT_EQUIVALENT_REWARD, grade
from cologic.grader.ppa import _cell_count_from_stat, yosys_available


def test_golden_is_equivalent_to_itself():
    r = grade(MUL8_BASELINE, mul8)
    assert r.info["equivalent"] is True
    assert r.info["eq_passed"] == r.info["eq_total"] > 0
    assert r.reward >= EQUIV_BASE


def test_good_rewrite_passes_the_gate():
    r = grade(MUL8_GOOD, mul8)
    assert r.info["equivalent"] is True
    assert r.reward >= EQUIV_FLOOR
    assert r.reward > NOT_EQUIVALENT_REWARD


def test_broken_rewrite_is_caught():
    """The whole point of the floor: a wrong circuit gets no PPA credit."""
    r = grade(MUL8_BROKEN, mul8)
    assert r.info["equivalent"] is False
    assert r.info["compiled"] is True
    assert r.info["stage"] == "not_equivalent"
    assert r.reward == NOT_EQUIVALENT_REWARD


def test_garbage_gets_no_module():
    r = grade("I cannot help with that.", mul8)
    assert r.info["stage"] == "no_module"
    assert r.reward == 0.0


def test_noncompiling_gets_compile_floor():
    r = grade("module mul8(input [7:0] a); assign p = ; endmodule", mul8)
    assert r.info["compiled"] is False
    assert r.info["stage"] == "compile_error"
    assert r.reward == pytest.approx(0.05)


def test_yosys_cell_count_parser_accepts_old_and_new_stat_formats():
    old = """
=== mul8 ===
   Number of cells:                 42
"""
    new = """
=== mul8 ===

        +----------Local Count, excluding submodules.
        |
      362 cells
       95   $_ANDNOT_
"""
    assert _cell_count_from_stat(old) == 42
    assert _cell_count_from_stat(new) == 362


@pytest.mark.skipif(not yosys_available(), reason="yosys not on PATH (PPA runs in Modal)")
def test_good_rewrite_gets_ppa_score_when_yosys_is_present():
    """When Yosys is present, equivalent rewrites get area metrics and PPA reward."""
    r = grade(MUL8_GOOD, mul8)
    assert r.info["stage"] == "graded"
    assert r.info["cand_cells"] is not None and r.info["ref_cells"] is not None
    expected = EQUIV_BASE + 0.5 * r.info["area_improvement"]
    expected = max(EQUIV_FLOOR, min(1.0, expected))
    assert r.reward == pytest.approx(round(expected, 6))
    assert r.reward >= EQUIV_FLOOR
