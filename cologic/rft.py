"""Dataset helpers for Fireworks reinforcement fine-tuning.

The evaluator still calls the locked reward seam:

    grade(completion: str, task: Task) -> GradeResult

This module only turns Tasks into Eval Protocol JSONL rows.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

from cologic.designs import BY_ID as OPT_BY_ID
from cologic.designs import OPT_TASKS
from cologic.prompt import build_messages, build_optimize_messages
from cologic.schema import Task
from cologic.tasks import BY_ID, GRADIENT_TASKS, HELDOUT_TASKS, SEED_TASKS, TRAIN_TASKS

DEFAULT_RFT_TASK_IDS = [t.task_id for t in TRAIN_TASKS + GRADIENT_TASKS]
DEFAULT_SMOKE_TASK_IDS = ["mux2", "vg_npu_int34_to_fp32"]


def task_to_row(task: Task, *, include_golden: bool = False) -> dict:
    """Return one Eval Protocol JSONL row for a task."""
    messages = build_messages(task)
    if include_golden:
        messages = [*messages, {"role": "assistant", "content": f"```verilog\n{task.reference_rtl}\n```"}]

    return {
        "messages": messages,
        "input_metadata": {
            "row_id": task.task_id,
            "dataset_info": {
                "task_id": task.task_id,
                "top_module": task.top_module,
                "held_out": task.held_out,
                "clocked": task.clocked,
                "tags": list(task.tags),
            },
        },
    }


def rows_for_task_ids(task_ids: Iterable[str], *, include_golden: bool = False) -> list[dict]:
    rows = []
    for task_id in task_ids:
        try:
            task = BY_ID[task_id]
        except KeyError as exc:
            known = ", ".join(sorted(BY_ID))
            raise KeyError(f"unknown task_id {task_id!r}; known task ids: {known}") from exc
        rows.append(task_to_row(task, include_golden=include_golden))
    return rows


def opt_task_to_row(task: Task, *, include_golden: bool = False) -> dict:
    """One Eval Protocol row for the OPTIMIZATION objective.

    The prompt asks the policy to rewrite `task.reference_rtl` smaller (same
    interface); the evaluator grades the completion with the gate-then-climb
    grader (equivalence + Yosys PPA). `include_golden` seeds the baseline itself
    as the assistant turn — it is equivalent, so it scores the equivalence floor,
    a clean smoke signal.
    """
    messages = build_optimize_messages(task)
    if include_golden:
        messages = [*messages, {"role": "assistant", "content": f"```verilog\n{task.reference_rtl}\n```"}]
    return {
        "messages": messages,
        "input_metadata": {
            "row_id": task.task_id,
            "dataset_info": {
                "task_id": task.task_id,
                "top_module": task.top_module,
                "held_out": task.held_out,
                "clocked": task.clocked,
                "tags": list(task.tags),
                "objective": "optimize",
            },
        },
    }


def opt_rows_for_task_ids(task_ids: Iterable[str], *, include_golden: bool = False) -> list[dict]:
    rows = []
    for task_id in task_ids:
        try:
            task = OPT_BY_ID[task_id]
        except KeyError as exc:
            known = ", ".join(sorted(OPT_BY_ID))
            raise KeyError(f"unknown optimization task_id {task_id!r}; known: {known}") from exc
        rows.append(opt_task_to_row(task, include_golden=include_golden))
    return rows


def opt_split_task_ids(split: str) -> list[str]:
    """Optimization task splits. `opt` = all curated optimization designs."""
    if split in ("opt", "all"):
        return [t.task_id for t in OPT_TASKS]
    if split == "smoke":
        return [t.task_id for t in OPT_TASKS[: min(2, len(OPT_TASKS))]]
    raise ValueError(f"unknown optimization split {split!r}")


def write_jsonl(rows: Iterable[dict], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    return out


def split_task_ids(split: str) -> list[str]:
    if split == "train":
        return [t.task_id for t in TRAIN_TASKS]
    if split == "gradient":
        return [t.task_id for t in GRADIENT_TASKS]
    if split == "rft":
        return list(DEFAULT_RFT_TASK_IDS)
    if split == "heldout":
        return [t.task_id for t in HELDOUT_TASKS]
    if split == "all":
        return [t.task_id for t in SEED_TASKS]
    if split == "smoke":
        return list(DEFAULT_SMOKE_TASK_IDS)
    raise ValueError(f"unknown split {split!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write Eval Protocol JSONL for Cologic RFT.")
    parser.add_argument("--out", required=True, help="Output JSONL path.")
    parser.add_argument(
        "--split",
        choices=["train", "gradient", "rft", "heldout", "all", "smoke"],
        default="rft",
        help="Task set to write.",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        dest="task_ids",
        help="Specific task id to include. May be passed multiple times.",
    )
    parser.add_argument(
        "--include-golden",
        action="store_true",
        help="Append each task's reference RTL as an assistant message for evaluator smoke tests.",
    )
    args = parser.parse_args(argv)

    task_ids = args.task_ids if args.task_ids else split_task_ids(args.split)
    out = write_jsonl(rows_for_task_ids(task_ids, include_golden=args.include_golden), args.out)
    print(f"wrote {len(task_ids)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
