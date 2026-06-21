"""The measurement tool itself: does `measure_gap` correctly isolate what the
search/repair loop adds beyond a single zero-shot sample?

This is a tool test, not a capability claim — it uses a stub policy + injected
grader so the gap is known by construction. The real, non-circular capability
number comes from running `measure_gap` on the live policy + Yosys (Modal).
"""

from __future__ import annotations

import re

from cologic.designs import tpu_matmul
from cologic.schema import GradeResult, Task
from harness import FlywheelConfig, HarnessConfig, measure_gap
from harness.measure import ZERO_SHOT_CONFIG


def _cells_grader(baseline_cells: int):
    """Grade by a `cells=N` marker; a `BROKEN` marker is rejected like the real gate."""
    def grade(rtl: str, _task: Task) -> GradeResult:
        if "BROKEN" in rtl:
            return GradeResult(0.10, {"stage": "not_equivalent", "compiled": True,
                                      "equivalent": False, "eq_passed": 1, "eq_total": 2})
        m = re.search(r"cells=(\d+)", rtl)
        cells = int(m.group(1)) if m else baseline_cells
        improvement = (baseline_cells - cells) / baseline_cells
        return GradeResult(0.5 + 0.5 * improvement, {
            "stage": "graded", "compiled": True, "equivalent": True,
            "ref_cells": baseline_cells, "cand_cells": cells, "area_improvement": improvement,
        })

    return grade


def test_measure_gap_credits_only_what_the_loop_adds():
    """Policy whose FIRST (zero-shot) sample is a broken rewrite, but which—given the
    repair turn and more generations—reaches a smaller equivalent design. The gap
    must attribute the win to the loop, not to zero-shot."""
    calls = {"n": 0}

    def model_fn(messages, *, temperature, max_tokens):
        # Repair turns hand back a valid, smaller design.
        if any("rejected" in m["content"].lower() for m in messages):
            return "module tt_um_tpu(); // cells=4"
        calls["n"] += 1
        # First sample (used by zero-shot, n=1, no repair) is broken; later samples shrink.
        if calls["n"] == 1:
            return "module tt_um_tpu(); // BROKEN"
        return f"module tt_um_tpu(); // cells={max(4, 9 - calls['n'])}"

    res = measure_gap(
        tpu_matmul,
        model_fn=model_fn,
        grader=_cells_grader(baseline_cells=10),
        zero_shot_config=ZERO_SHOT_CONFIG,
        loop_config=FlywheelConfig(max_generations=8, patience=2,
                                   harness=HarnessConfig(n_candidates=2, temperature=0.0,
                                                         max_repair_rounds=1)),
    )

    assert res.baseline_cells == 10
    # Zero-shot's single sample was broken -> it can only fall back to the baseline.
    assert res.zero_shot.cells == 10
    # The loop repaired/searched its way to a genuinely smaller equivalent design.
    assert res.loop.cells is not None and res.loop.cells < 10
    assert res.loop.equivalent is True
    assert res.loop_beats_zero_shot is True
    assert res.gap_cells == res.zero_shot.cells - res.loop.cells > 0


def test_measure_gap_reports_no_gain_when_zero_shot_already_optimal():
    """If the first sample is already the best the policy can do, the loop adds
    nothing and the gap is zero — the measurement must not manufacture a win."""
    def model_fn(messages, *, temperature, max_tokens):
        return "module tt_um_tpu(); // cells=5"  # same design every time

    res = measure_gap(
        tpu_matmul,
        model_fn=model_fn,
        grader=_cells_grader(baseline_cells=10),
        loop_config=FlywheelConfig(max_generations=5, patience=2,
                                   harness=HarnessConfig(n_candidates=2, temperature=0.0,
                                                         max_repair_rounds=0)),
    )

    assert res.zero_shot.cells == 5
    assert res.loop.cells == 5
    assert res.gap_cells == 0
    assert res.loop_beats_zero_shot is False
