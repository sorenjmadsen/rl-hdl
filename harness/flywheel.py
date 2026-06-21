"""Single-design optimization flywheel — run the harness on ONE design until it plateaus.

Autoresearch-style loop (karpathy/autoresearch): one artifact, one metric, iterate
until improvement stops. Here the artifact is a Verilog design, the metric is
post-synthesis gate count (Yosys), and the proposer is the MAGE harness.

    gen 0: baseline                      -> best = baseline
    gen g: harness tries to beat `best`  -> if it finds a smaller EQUIVALENT
                                            design, adopt it; else mark stale
    stop:  `patience` consecutive non-improving generations  -> plateau

Equivalence guard (locked): every candidate is graded against the ORIGINAL design
as the oracle, never against the current best. We show the best-so-far to the
*model* (as the thing to beat), but the immutable grader always checks
equivalence to `task.reference_rtl`, so equivalence cannot drift across
generations even though random-vector checking isn't exhaustive.

The model is injected (offline-testable); on Modal it's the Fireworks policy and
the grader has Yosys, so the gate-count curve is real.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from cologic.grader import grade as default_grade
from cologic.schema import GradeResult, Task
from harness.optimizer import GraderFn, HarnessConfig, ModelFn, optimize


@dataclass
class FlywheelConfig:
    """Loop controls for one design. `harness` is the per-generation proposer config."""

    max_generations: int = 12
    patience: int = 3           # stop after this many non-improving generations
    min_delta_cells: int = 1    # a generation must cut at least this many cells to count
    harness: HarnessConfig = field(default_factory=HarnessConfig)


@dataclass
class Generation:
    gen: int
    best_rtl: str
    reward: float
    cells: int | None
    equivalent: bool
    improved: bool  # did this generation beat the previous best?


@dataclass
class FlywheelResult:
    task_id: str
    best_rtl: str
    best_cells: int | None
    baseline_cells: int | None
    history: list[Generation] = field(default_factory=list)
    plateaued: bool = False

    @property
    def total_improvement(self) -> float | None:
        if not self.baseline_cells or self.best_cells is None:
            return None
        return (self.baseline_cells - self.best_cells) / self.baseline_cells


def _cells(info: dict) -> int | None:
    """Candidate gate count from a grade info dict (falls back to ref for the baseline)."""
    c = info.get("cand_cells")
    return c if c is not None else info.get("ref_cells")


def run_flywheel(
    task: Task,
    *,
    model_fn: ModelFn,
    grader: GraderFn | None = None,
    config: FlywheelConfig | None = None,
) -> FlywheelResult:
    """Optimize `task`'s design until its gate count plateaus. Returns the trajectory."""
    cfg = config or FlywheelConfig()
    grade = grader or default_grade

    # Oracle: always grade against the ORIGINAL design, whatever we show the model.
    def oracle(rtl: str, _ignored: Task | None = None) -> GradeResult:
        return grade(rtl, task)

    base = oracle(task.reference_rtl)
    best_rtl = task.reference_rtl
    best_cells = _cells(base.info)
    best_reward = base.reward
    baseline_cells = best_cells

    history = [Generation(0, best_rtl, best_reward, best_cells,
                          bool(base.info.get("equivalent", True)), False)]
    stale = 0

    for g in range(1, cfg.max_generations + 1):
        # Show the harness the best-so-far as the design to beat; grade vs original.
        prompt_task = replace(task, reference_rtl=best_rtl)
        res = optimize(prompt_task, model_fn=model_fn, grader=oracle, config=cfg.harness)
        cand = res.best
        cells = cand.info.get("cand_cells")

        improved = bool(
            cand.equivalent
            and cells is not None
            and best_cells is not None
            and cells <= best_cells - cfg.min_delta_cells
        )
        if improved:
            best_rtl, best_cells, best_reward, stale = cand.rtl, cells, cand.reward, 0
        else:
            stale += 1

        history.append(Generation(g, best_rtl, best_reward, best_cells, cand.equivalent, improved))
        if stale >= cfg.patience:
            break

    return FlywheelResult(
        task_id=task.task_id,
        best_rtl=best_rtl,
        best_cells=best_cells,
        baseline_cells=baseline_cells,
        history=history,
        plateaued=stale >= cfg.patience,
    )


def demo() -> None:
    """Offline check (no API, no tools): a stub policy that proposes progressively
    smaller designs down to a floor; assert the flywheel rides it down and plateaus."""
    import re

    from cologic.schema import Port

    START, FLOOR = 12, 4
    task = Task(
        task_id="demo", spec="x", top_module="m",
        interface=[Port("a", "input"), Port("b", "input"), Port("y", "output")],
        reference_rtl="module m(input a, input b, output y); assign y = a & b; endmodule",
    )

    state = {"n": 0}

    def stub_model(messages, *, temperature, max_tokens):
        n = state["n"]
        state["n"] += 1
        cells = max(FLOOR, START - n)
        return f"module m(input a, input b, output y); assign y = a & b; // cells={cells}"

    def stub_grader(rtl: str, _task: Task) -> GradeResult:
        m = re.search(r"cells=(\d+)", rtl)
        cells = int(m.group(1)) if m else START
        improvement = (START - cells) / START
        return GradeResult(0.5 + 0.5 * improvement, {
            "stage": "graded", "equivalent": True,
            "cand_cells": cells, "ref_cells": START, "area_improvement": improvement,
        })

    res = run_flywheel(task, model_fn=stub_model, grader=stub_grader,
                       config=FlywheelConfig(max_generations=20, patience=3,
                                             harness=HarnessConfig(n_candidates=2, max_repair_rounds=0)))
    assert res.plateaued, res
    assert res.best_cells == FLOOR, res.best_cells
    assert res.baseline_cells == START, res.baseline_cells
    curve = [g.cells for g in res.history]
    print(f"demo ok: cells {curve} over {len(res.history)} gens, "
          f"plateaued at {res.best_cells} (baseline {res.baseline_cells}, "
          f"improvement {res.total_improvement:.0%})")


if __name__ == "__main__":
    demo()
