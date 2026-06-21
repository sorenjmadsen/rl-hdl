"""Eval orchestration: pass@1 + mean dense reward over a task set.

Grader-agnostic. `evaluate` takes a `grade_batch` callable so the same logic runs
against the local in-process grader (fast iteration) or the Modal parallel grader
(scale). This is the floor's headline-number machinery and the demo's red/green
source of truth.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from cologic.schema import Task

# A grader maps (task, completion) pairs -> result dicts: {reward, info, ...}.
GradeBatch = Callable[[list[tuple[Task, str]]], list[dict]]


def _is_pass(result: dict) -> bool:
    info = result.get("info", {})
    return info.get("stage") == "graded" and info.get("total", 0) > 0 and info["passed"] == info["total"]


@dataclass
class TaskEval:
    task_id: str
    n: int
    n_pass: int
    pass_rate: float        # fraction of this task's samples that fully pass
    mean_reward: float
    rewards: list[float] = field(default_factory=list)


@dataclass
class EvalReport:
    model: str
    n_per_task: int
    pass_at_1: float        # mean over tasks of pass_rate (unbiased pass@1)
    mean_reward: float
    per_task: list[TaskEval]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def table(self) -> str:
        w = max(len(t.task_id) for t in self.per_task) if self.per_task else 8
        lines = [f"{'task'.ljust(w)}  pass    mean_reward"]
        for t in self.per_task:
            lines.append(f"{t.task_id.ljust(w)}  {t.n_pass}/{t.n:<4}  {t.mean_reward:.3f}")
        lines.append("-" * (w + 22))
        lines.append(f"{'pass@1'.ljust(w)}  {self.pass_at_1:.3f}   mean {self.mean_reward:.3f}")
        return "\n".join(lines)


def evaluate(pairs: list[tuple[Task, str]], grade_batch: GradeBatch, *, model: str = "?") -> EvalReport:
    """Grade pre-sampled (task, completion) pairs and aggregate by task."""
    results = grade_batch(pairs)
    assert len(results) == len(pairs), "grader must return one result per pair"

    by_task: dict[str, list[tuple[Task, dict]]] = {}
    for (task, _), res in zip(pairs, results):
        by_task.setdefault(task.task_id, []).append((task, res))

    per_task: list[TaskEval] = []
    for task_id, items in by_task.items():
        rewards = [r["reward"] for _, r in items]
        n_pass = sum(_is_pass(r) for _, r in items)
        per_task.append(
            TaskEval(
                task_id=task_id,
                n=len(items),
                n_pass=n_pass,
                pass_rate=n_pass / len(items),
                mean_reward=sum(rewards) / len(rewards),
                rewards=rewards,
            )
        )

    n_per_task = max((t.n for t in per_task), default=0)
    pass_at_1 = sum(t.pass_rate for t in per_task) / len(per_task) if per_task else 0.0
    mean_reward = sum(t.mean_reward for t in per_task) / len(per_task) if per_task else 0.0
    return EvalReport(model=model, n_per_task=n_per_task, pass_at_1=pass_at_1, mean_reward=mean_reward, per_task=per_task)


def local_grade_batch(pairs: list[tuple[Task, str]]) -> list[dict]:
    """In-process grader (no Modal). Good for smoke tests and small evals."""
    from cologic.verifier import grade

    out = []
    for task, completion in pairs:
        r = grade(completion, task)
        out.append({"reward": r.reward, "info": r.info, "task_id": task.task_id})
    return out
