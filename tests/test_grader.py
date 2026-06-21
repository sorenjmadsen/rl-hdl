"""Floor proof: the equivalence gate catches a subtly-broken rewrite.

These run on Verilator alone (installed locally). The Yosys PPA stage is exercised
separately in the Modal image; here an equivalent design lands at EQUIV_BASE with
stage "equivalent_no_ppa" when yosys is absent, or "graded" when it is present.
"""

from __future__ import annotations

import pytest

from cologic.designs import MUL8_BASELINE, MUL8_BROKEN, MUL8_GOOD, mul8
from cologic.grader import (
    COMPILE_ERROR_REWARD,
    EQUIV_BASE,
    EQUIV_FLOOR,
    NOT_EQUIVALENT_REWARD,
    grade,
)
from cologic.grader.ppa import (
    _cell_count_from_stat,
    _chip_area_from_stat,
    liberty_path,
    yosys_available,
)


def test_golden_is_equivalent_to_itself():
    r = grade(MUL8_BASELINE, mul8)
    assert r.info["equivalent"] is True
    assert r.info["eq_passed"] == r.info["eq_total"] > 0
    assert r.reward >= EQUIV_BASE


def test_yosys_synth_failure_scores_not_crashes(monkeypatch):
    """A candidate that passes Verilator equivalence but trips Yosys synthesis must
    score as a synth failure (low, never a winner) — never raise, or it crashes the
    whole harness (the gen_2 SIA crash). Verilator runs for real; we simulate the
    Yosys failure so the test is deterministic without yosys installed."""
    from cologic.grader.ppa import YosysUnavailable  # noqa: F401 — ensure import path

    def boom(*_a, **_k):
        raise RuntimeError("yosys failed (rc=1):\ndesign.sv:3: ERROR: syntax error, unexpected '['")

    monkeypatch.setattr("cologic.grader.synth_cells", boom)
    r = grade(MUL8_GOOD, mul8)  # MUL8_GOOD is genuinely equivalent under Verilator
    assert r.info["equivalent"] is True          # equivalence still passed
    assert r.info["stage"] == "synth_error"
    assert r.reward == COMPILE_ERROR_REWARD       # low; loses to any real equivalent design
    assert "yosys FAILED" in r.info["log"]


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


def test_chip_area_parser_accepts_module_and_top_module_forms():
    module = "   Chip area for module '\\mul8': 1234.567800\n"
    top = "Chip area for top module '\\tt_um_tpu': 98765.4321\n"
    assert _chip_area_from_stat(module) == pytest.approx(1234.5678)
    assert _chip_area_from_stat(top) == pytest.approx(98765.4321)
    assert _chip_area_from_stat("no area reported here") is None


def test_liberty_path_resolves_only_existing_files(tmp_path, monkeypatch):
    monkeypatch.delenv("RLHDL_LIBERTY", raising=False)
    assert liberty_path() is None
    monkeypatch.setenv("RLHDL_LIBERTY", str(tmp_path / "missing.lib"))
    assert liberty_path() is None
    lib = tmp_path / "cells.lib"
    lib.write_text("/* liberty stub */")
    monkeypatch.setenv("RLHDL_LIBERTY", str(lib))
    assert liberty_path() == str(lib)


def test_area_um2_keys_are_present_and_none_without_liberty(monkeypatch):
    """The *_um2 info keys are part of the stable contract and stay None (reward
    untouched) when no liberty library is configured."""
    monkeypatch.delenv("RLHDL_LIBERTY", raising=False)
    r = grade(MUL8_GOOD, mul8)
    assert r.info["equivalent"] is True
    for key in ("ref_area_um2", "cand_area_um2", "area_um2_improvement"):
        assert key in r.info and r.info[key] is None
    assert r.reward >= EQUIV_BASE  # real-area observation never lowers the reward


@pytest.mark.skipif(
    not (yosys_available() and liberty_path()),
    reason="real-area metric needs yosys + RLHDL_LIBERTY (runs in the Modal image)",
)
def test_real_area_um2_is_measured_when_liberty_is_present():
    """With a liberty lib, equivalent designs get real um^2 area — observe-only,
    so the reward must still equal the cell-count climb."""
    r = grade(MUL8_GOOD, mul8)
    assert r.info["stage"] == "graded"
    assert r.info["ref_area_um2"] is not None and r.info["cand_area_um2"] is not None
    assert r.info["area_um2_improvement"] is not None
    expected = max(EQUIV_FLOOR, min(1.0, EQUIV_BASE + 0.5 * r.info["area_improvement"]))
    assert r.reward == pytest.approx(round(expected, 6))
