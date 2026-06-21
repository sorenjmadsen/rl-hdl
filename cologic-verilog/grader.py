"""Hand-built EvaluationResult that preserves the hidden grader's hard cap."""

import importlib.util
from pathlib import Path
from typing import Any

from hud.graders import EvaluationResult, SubScore  # v6 home (was hud.tools.types)

from scenario_helpers import WORKSPACE_ROOT, hidden_dir as _hidden_dir
from task_catalog import TASK_SPECS_BY_ID


def _load_grade_module(task_id: str, hidden_dir: Path):
    grade_path = hidden_dir / "grade.py"
    spec = importlib.util.spec_from_file_location(f"{task_id}_hidden_grade", grade_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import hidden grader at {grade_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _subscores_from_result(result: dict[str, Any]) -> list[SubScore]:
    subscores = []
    for name, data in result.get("subscores", {}).items():
        raw_value = data.get("raw_score")
        if raw_value is None:
            weight = float(data.get("weight", 1.0))
            raw_value = float(data.get("weighted_score", 0.0)) / weight if weight else 0.0
        subscores.append(
            SubScore(
                name=name,
                weight=float(data.get("weight", 0.0)),
                value=max(0.0, min(1.0, float(raw_value or 0.0))),
                metadata=data.get("result"),
            )
        )
    return subscores


def evaluate_task(task_id: str) -> EvaluationResult:
    task_spec = TASK_SPECS_BY_ID[task_id]
    workdir = WORKSPACE_ROOT
    hidden_dir = _hidden_dir(task_id)
    grade_mod = _load_grade_module(task_id, hidden_dir)
    try:
        result: dict[str, Any] = grade_mod.grade(
            workdir,
            rtl_override=None,
            hidden_root=hidden_dir,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed; never error the episode
        # A missing/renamed editable file or any grader crash must score 0, not raise out
        # and error the rollout: an agent WILL delete the target file, and that should be a
        # 0, not a failed run. (Reproduced: missing props -> FileNotFoundError -> episode error.)
        return EvaluationResult(
            reward=0.0,
            done=True,
            content=f"{task_id}: submission could not be graded ({type(exc).__name__}: {exc})",
            info={
                "task_id": task_id,
                "module": task_spec.module,
                "track": task_spec.track,
                "hard_caps": ["grader_error"],
                "error": f"{type(exc).__name__}: {exc}",
                "workdir": str(workdir),
                "hidden_dir": str(hidden_dir),
            },
            subscores=[],
        )

    # Build EvaluationResult by hand: do NOT route through hud.graders.combine(),
    # which renormalizes positive weights and would erase the grader's hard cap
    # (functional==0 -> reward forced to 0). The negative-weight hard_cap_penalty subscore
    # reconciles the displayed subscores to the capped reward.
    subscores = _subscores_from_result(result)
    weighted_sum = sum(subscore.weight * subscore.value for subscore in subscores)
    reward = float(result.get("reward", 0.0))
    if reward + 1e-9 < weighted_sum:
        subscores.append(
            SubScore(
                name="hard_cap_penalty",
                weight=reward - weighted_sum,
                value=1.0,
                metadata={"hard_caps": result.get("hard_caps", [])},
            )
        )

    return EvaluationResult(
        reward=reward,
        done=True,
        content=f"{task_id} graded",
        info={
            "task_id": task_id,
            "module": task_spec.module,
            "track": task_spec.track,
            "hard_caps": result.get("hard_caps", []),
            "workdir": str(workdir),
            "hidden_dir": str(hidden_dir),
        },
        subscores=subscores,
    )
