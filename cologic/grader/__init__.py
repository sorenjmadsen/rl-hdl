"""The immutable grader: the ONLY authority that computes reward.

    grade(candidate_rtl, task) -> GradeResult(reward, info)

This module is import-only and sits OUTSIDE everything the system may mutate.
SIA may evolve the MAGE harness; ES may move the LoRA weights; neither may touch
this code. The reward physically cannot be faked: the circuit is equivalent to
the golden reference and smaller, or it isn't.

Gate, then climb (never blended into one opaque scalar):

    no module extracted        -> 0.00
    extracted, won't compile   -> 0.05   (syntactic-validity partial credit)
    compiles, NOT equivalent   -> 0.10   (no PPA credit — wrong circuit)
    equivalent                 -> EQUIV_BASE + ALPHA * area_improvement
                                  (clamped to [EQUIV_FLOOR, 1.0])

area_improvement = (ref_cells - cand_cells) / ref_cells, via Yosys, computed
only among equivalent survivors. If Yosys is unavailable (e.g. local dev box),
an equivalent design scores exactly EQUIV_BASE and info["stage"] is
"equivalent_no_ppa" — the equivalence gate still runs and still demos.
"""

from __future__ import annotations

from cologic.grader.equivalence import check_equivalence
from cologic.grader.ppa import YosysUnavailable, synth_cells
from cologic.schema import GradeResult, Task

__all__ = ["grade", "GradeResult", "Task", "check_equivalence", "synth_cells"]

NO_MODULE_REWARD = 0.00
COMPILE_ERROR_REWARD = 0.05
NOT_EQUIVALENT_REWARD = 0.10
EQUIV_BASE = 0.50   # reward for an equivalent design with no area win
EQUIV_FLOOR = 0.30  # equivalent-but-bloated still beats not-equivalent (0.10)
ALPHA = 0.50        # PPA weight; equivalent + 100%-smaller -> 1.0 (unreachable)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def grade(candidate_rtl: str, task: Task, *, timeout: float = 60.0) -> GradeResult:
    """Grade a candidate rewrite of `task.reference_rtl`. The locked reward seam.

    info keys (stable contract for logging / the train-vs-heldout gap check):
      stage           : no_module | compile_error | sim_error | not_equivalent
                        | equivalent_no_ppa | graded
      compiled        : bool
      equivalent      : bool
      eq_passed       : int    (output x vector comparisons that matched)
      eq_total        : int
      ref_cells       : int|None  (golden reference gate count)
      cand_cells      : int|None  (candidate gate count)
      area_improvement: float|None  (fraction smaller than reference; <0 = bigger)
      log             : str    (tool output, truncated)
    """
    eq = check_equivalence(candidate_rtl, task, timeout=timeout)

    base_info = {
        "stage": eq.stage,
        "compiled": eq.compiled,
        "equivalent": eq.equivalent,
        "eq_passed": eq.passed,
        "eq_total": eq.total,
        "ref_cells": None,
        "cand_cells": None,
        "area_improvement": None,
        "log": eq.log,
    }

    if eq.stage == "no_module":
        return GradeResult(NO_MODULE_REWARD, base_info)
    if eq.stage == "compile_error":
        return GradeResult(COMPILE_ERROR_REWARD, base_info)
    if eq.stage == "sim_error" or not eq.equivalent:
        if eq.stage == "checked":
            base_info["stage"] = "not_equivalent"
        return GradeResult(NOT_EQUIVALENT_REWARD, base_info)

    # Equivalent: climb on PPA among equivalent survivors only.
    try:
        ref = synth_cells(task.reference_rtl, task.top_module, timeout=timeout)
        cand = synth_cells(eq.candidate, task.top_module, timeout=timeout)
    except YosysUnavailable:
        base_info["stage"] = "equivalent_no_ppa"
        return GradeResult(EQUIV_BASE, base_info)

    improvement = (ref.cells - cand.cells) / ref.cells if ref.cells else 0.0
    reward = _clamp(EQUIV_BASE + ALPHA * improvement, EQUIV_FLOOR, 1.0)
    base_info.update(
        stage="graded",
        ref_cells=ref.cells,
        cand_cells=cand.cells,
        area_improvement=round(improvement, 6),
        log=(eq.log + "\n--- yosys(cand) ---\n" + cand.log)[-4000:],
    )
    return GradeResult(round(reward, 6), base_info)
