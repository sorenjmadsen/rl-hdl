"""The headline experiment: does the loop exceed the bare LLM?

A single passing test of "the flywheel found a smaller design" proves nothing on
its own — the model might have produced that design zero-shot. What earns the
project's thesis is the *gap*: the same policy and the same immutable grader, run
two ways, on a design whose optimum we did NOT author.

    baseline   : the real RTL, synthesized as-is (the thing to beat)
    zero-shot  : ONE greedy sample from the policy (n=1, no repair, temp 0)
    full loop  : the multi-candidate, multi-generation flywheel run to plateau

All three are scored only by `cologic.grader` (Verilator equivalence + Yosys gate
count). `gap_cells = zero_shot_cells - loop_cells` is the cells the *search/repair
machinery* bought beyond a bare sample. If it's ~0, the harness adds nothing; if
it's large, the system optimizes past what the model emits on its own — the unlock.

The policy is injected (`model_fn`), so the measurement is testable offline with a
stub and runs for real on Modal with the Fireworks policy + Yosys.
"""

from __future__ import annotations

from dataclasses import dataclass

from cologic.grader import grade as default_grade
from cologic.schema import GradeResult, Task
from harness.flywheel import FlywheelConfig, run_flywheel
from harness.optimizer import GraderFn, HarnessConfig, ModelFn, optimize

# Zero-shot control: one greedy sample, no repair loop, no diversity. This is "the
# bare LLM's answer," with the equivalence gate only as a safety net (a broken or
# bigger sample falls back to the baseline, never below it).
ZERO_SHOT_CONFIG = HarnessConfig(
    n_candidates=1, temperature=0.0, max_repair_rounds=0, keep_baseline=True,
)


@dataclass
class Arm:
    """One measured optimizer setting."""

    name: str
    cells: int | None
    reward: float
    equivalent: bool
    rtl: str

    def improvement_over(self, baseline_cells: int | None) -> float | None:
        if not baseline_cells or self.cells is None:
            return None
        return (baseline_cells - self.cells) / baseline_cells


@dataclass
class GapResult:
    task_id: str
    baseline_cells: int | None
    zero_shot: Arm
    loop: Arm

    @property
    def gap_cells(self) -> int | None:
        """Cells the loop saved beyond the zero-shot sample (>0 => loop wins)."""
        if self.zero_shot.cells is None or self.loop.cells is None:
            return None
        return self.zero_shot.cells - self.loop.cells

    @property
    def loop_beats_zero_shot(self) -> bool:
        g = self.gap_cells
        return g is not None and g > 0 and self.loop.equivalent


def _cells(info: dict) -> int | None:
    c = info.get("cand_cells")
    return c if c is not None else info.get("ref_cells")


def measure_gap(
    task: Task,
    *,
    model_fn: ModelFn,
    grader: GraderFn | None = None,
    loop_config: FlywheelConfig | None = None,
    zero_shot_config: HarnessConfig | None = None,
) -> GapResult:
    """Run baseline / zero-shot / full-loop on `task` and return the three-way gap.

    The grader (immutable by default) is the only judge; we never assert the
    optimum. Equivalence in every arm is checked against `task.reference_rtl`.
    """
    grade = grader or default_grade

    base = grade(task.reference_rtl, task)
    baseline_cells = _cells(base.info)

    # Zero-shot: one greedy structural-rewrite attempt.
    zs = optimize(task, model_fn=model_fn, grader=grade,
                  config=zero_shot_config or ZERO_SHOT_CONFIG)
    zero_shot = Arm("zero-shot", _cells(zs.best.info), zs.best.reward,
                    zs.best.equivalent, zs.best.rtl)

    # Full loop: the flywheel to plateau. Re-grade the winner once for its final
    # reward/equivalence (the flywheel tracks cells, not the full GradeResult).
    fly = run_flywheel(task, model_fn=model_fn, grader=grade, config=loop_config)
    best = grade(fly.best_rtl, task)
    loop = Arm("full-loop", fly.best_cells, best.reward,
               best.info.get("equivalent", False), fly.best_rtl)

    return GapResult(task.task_id, baseline_cells, zero_shot, loop)


def format_gap(res: GapResult) -> str:
    """A compact three-row table for the demo."""
    def row(name: str, arm_cells: int | None, imp: float | None, equiv) -> str:
        cells = "n/a" if arm_cells is None else str(arm_cells)
        win = "" if imp is None else f"{imp * 100:+.1f}%"
        return f"{name:<12} {cells:>7} {win:>9} {str(equiv):>6}"

    lines = [
        f"\noptimization gap on {res.task_id}",
        f"{'arm':<12} {'cells':>7} {'vs base':>9} {'equiv':>6}",
        "-" * 38,
        row("baseline", res.baseline_cells, 0.0 if res.baseline_cells else None, True),
        row("zero-shot", res.zero_shot.cells,
            res.zero_shot.improvement_over(res.baseline_cells), res.zero_shot.equivalent),
        row("full-loop", res.loop.cells,
            res.loop.improvement_over(res.baseline_cells), res.loop.equivalent),
    ]
    gap = res.gap_cells
    verdict = ("n/a" if gap is None
               else f"{gap:+d} cells ({'LOOP EXCEEDS ZERO-SHOT' if res.loop_beats_zero_shot else 'no gain over zero-shot'})")
    lines.append(f"\ngap (zero-shot - loop): {verdict}\n")
    return "\n".join(lines)
