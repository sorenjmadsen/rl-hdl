"""Eval Protocol reward function for Cologic Fireworks RFT — OPTIMIZATION objective.

This is the weight lever's reward: the policy is trained to rewrite a correct
module SMALLER while staying provably equivalent. Reward comes only from the
immutable gate-then-climb grader (Verilator equivalence + Yosys PPA) — no LLM
judge anywhere. Mirrors test_cologic_reward.py (generation), but:

  grade source : cologic.grader.grade(candidate_rtl, task)   (not verifier.grade)
  tasks        : cologic.designs.BY_ID (optimization designs, reference = baseline)
  metrics      : equivalent, area_improvement
"""

import json
import os
from pathlib import Path

from eval_protocol.models import EvaluateResult, EvaluationRow, MetricResult
from eval_protocol.pytest.default_single_turn_rollout_process import SingleTurnRolloutProcessor
from eval_protocol.pytest.evaluation_test import evaluation_test

from cologic.designs import BY_ID
from cologic.grader import grade

DATASET = Path(__file__).with_name("dataset.jsonl")
DEFAULT_ROLLOUT_MODEL = os.environ.get(
    "COLOGIC_RFT_ROLLOUT_MODEL",
    "accounts/fireworks/models/gemma-4-26b-a4b-it",
)
MAX_DATASET_ROWS = int(os.environ.get("COLOGIC_RFT_MAX_DATASET_ROWS", "0")) or None
MAX_OUTPUT_TOKENS = int(os.environ.get("COLOGIC_RFT_MAX_OUTPUT_TOKENS", "2048"))


def _task_id(row: EvaluationRow) -> str | None:
    info = row.input_metadata.dataset_info or {}
    return info.get("task_id") or row.input_metadata.row_id


def _completion(row: EvaluationRow) -> str:
    assistant_messages = [message for message in row.messages if message.role == "assistant"]
    if not assistant_messages:
        return ""
    content = assistant_messages[-1].content
    if isinstance(content, list):
        return "".join(str(part) for part in content)
    return str(content or "")


def _result_reason(task_id: str, reward: float, info: dict) -> str:
    summary = {
        "task_id": task_id,
        "reward": reward,
        "stage": info.get("stage"),
        "equivalent": info.get("equivalent"),
        "ref_cells": info.get("ref_cells"),
        "cand_cells": info.get("cand_cells"),
        "area_improvement": info.get("area_improvement"),
    }
    log = str(info.get("log") or "")
    if log:
        summary["log_tail"] = log[-1200:]
    return json.dumps(summary, sort_keys=True)


@evaluation_test(
    input_dataset=[str(DATASET)],
    completion_params=[
        {
            "model": DEFAULT_ROLLOUT_MODEL,
            "temperature": 0.7,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
    ],
    rollout_processor=SingleTurnRolloutProcessor(),
    aggregation_method="mean",
    passed_threshold=0.5,  # an equivalent design scores >= EQUIV_BASE (0.5)
    max_dataset_rows=MAX_DATASET_ROWS,
    num_runs=1,
    mode="pointwise",
)
def test_cologic_optimize_reward(row: EvaluationRow) -> EvaluationRow:
    task_id = _task_id(row)
    if not task_id or task_id not in BY_ID:
        row.evaluation_result = EvaluateResult(
            score=0.0,
            reason=f"Unknown optimization task_id in dataset metadata: {task_id!r}",
            is_score_valid=False,
        )
        return row

    completion = _completion(row)
    if not completion:
        row.evaluation_result = EvaluateResult(
            score=0.0,
            reason=f"No assistant completion for task {task_id}",
            is_score_valid=True,
        )
        return row

    result = grade(completion, BY_ID[task_id])
    info = dict(result.info)
    equivalent = bool(info.get("equivalent"))
    improvement = info.get("area_improvement")

    row.evaluation_result = EvaluateResult(
        score=float(result.reward),
        reason=_result_reason(task_id, float(result.reward), info),
        metrics={
            "equivalent": MetricResult(
                score=1.0 if equivalent else 0.0,
                reason=str(info.get("stage") or "unknown"),
            ),
            "area_improvement": MetricResult(
                score=float(improvement) if improvement is not None else 0.0,
                reason=f"ref={info.get('ref_cells')} cand={info.get('cand_cells')} cells",
            ),
        },
    )
    return row


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-vs"]))
