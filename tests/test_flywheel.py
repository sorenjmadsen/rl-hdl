"""Single-design flywheel: rides a design's gate count down and stops at plateau."""

from __future__ import annotations

import re
import shutil

import pytest

from cologic.designs import mul8
from cologic.grader import EQUIV_BASE
from cologic.schema import GradeResult, Task
from harness import FlywheelConfig, HarnessConfig, run_flywheel
from harness.flywheel import demo


def _shrinking_policy(start: int, floor: int):
    """A stub policy that proposes designs of ever-fewer 'cells' down to `floor`."""
    state = {"n": 0}

    def model_fn(messages, *, temperature, max_tokens):
        cells = max(floor, start - state["n"])
        state["n"] += 1
        return f"module m(input a, input b, output y); assign y = a & b; // cells={cells}"

    return model_fn


def _cells_grader(start: int):
    def grade(rtl: str, _task: Task) -> GradeResult:
        m = re.search(r"cells=(\d+)", rtl)
        cells = int(m.group(1)) if m else start
        improvement = (start - cells) / start
        return GradeResult(0.5 + 0.5 * improvement, {
            "stage": "graded", "equivalent": True,
            "cand_cells": cells, "ref_cells": start, "area_improvement": improvement,
        })

    return grade


def test_flywheel_rides_down_and_plateaus():
    res = run_flywheel(
        mul8,
        model_fn=_shrinking_policy(12, 4),
        grader=_cells_grader(12),
        config=FlywheelConfig(max_generations=20, patience=3,
                              harness=HarnessConfig(n_candidates=2, max_repair_rounds=0)),
    )
    assert res.plateaued
    assert res.best_cells == 4              # rode down to the floor
    assert res.baseline_cells == 12
    assert res.total_improvement == pytest.approx((12 - 4) / 12)
    # cells are monotonically non-increasing across the trajectory
    cells = [g.cells for g in res.history]
    assert all(b <= a for a, b in zip(cells, cells[1:]))


def test_flywheel_stops_when_no_improvement():
    """A policy that never beats the baseline plateaus after exactly `patience` gens."""
    res = run_flywheel(
        mul8,
        model_fn=lambda *a, **k: "module mul8(input [7:0] a, input [7:0] b, output [15:0] p); assign p = a*b; endmodule",
        grader=_cells_grader(10),  # constant 10 cells -> never improves
        config=FlywheelConfig(max_generations=20, patience=2,
                              harness=HarnessConfig(n_candidates=1, max_repair_rounds=0)),
    )
    assert res.plateaued
    assert len(res.history) == 1 + 2  # gen 0 baseline + patience non-improving gens


def test_offline_demo_runs():
    demo()


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_flywheel_real_grader_no_yosys_plateaus_immediately():
    """With the real grader but no Yosys (local), cells are unknown so no generation
    can show improvement — the flywheel should plateau cleanly rather than loop forever."""
    res = run_flywheel(
        mul8,
        model_fn=lambda *a, **k: "module mul8(input [7:0] a, input [7:0] b, output [15:0] p); assign p = a*b; endmodule",
        config=FlywheelConfig(max_generations=5, patience=2,
                              harness=HarnessConfig(n_candidates=1, max_repair_rounds=0)),
    )
    assert res.plateaued
    assert res.history[0].reward >= EQUIV_BASE  # baseline is equivalent to itself
