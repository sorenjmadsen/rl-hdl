"""Eval Protocol reward function for Cologic Fireworks RFT."""

import json
import os
from pathlib import Path

from eval_protocol.models import EvaluateResult, EvaluationRow, MetricResult
from eval_protocol.pytest.evaluation_test import evaluation_test
from eval_protocol.pytest.default_single_turn_rollout_process import SingleTurnRolloutProcessor

from cologic.tasks import BY_ID
from cologic.verifier import grade

DATASET = Path(__file__).with_name("dataset.jsonl")
DEFAULT_ROLLOUT_MODEL = os.environ.get(
    "COLOGIC_RFT_ROLLOUT_MODEL",
    "accounts/fireworks/models/qwen3-0p6b",
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
        "compiled": info.get("compiled"),
        "passed": info.get("passed"),
        "total": info.get("total"),
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
    passed_threshold=0.1,
    max_dataset_rows=MAX_DATASET_ROWS,
    num_runs=1,
    mode="pointwise",
)
def test_cologic_verilog_reward(row: EvaluationRow) -> EvaluationRow:
    task_id = _task_id(row)
    if not task_id or task_id not in BY_ID:
        row.evaluation_result = EvaluateResult(
            score=0.0,
            reason=f"Unknown task_id in dataset metadata: {task_id!r}",
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
    total = int(info.get("total") or 0)
    passed = int(info.get("passed") or 0)
    matched_fraction = passed / total if total else 0.0
    compiled = bool(info.get("compiled"))

    row.evaluation_result = EvaluateResult(
        score=float(result.reward),
        reason=_result_reason(task_id, float(result.reward), info),
        metrics={
            "compiled": MetricResult(
                score=1.0 if compiled else 0.0,
                reason=str(info.get("stage") or "unknown"),
            ),
            "matched_fraction": MetricResult(
                score=matched_fraction,
                reason=f"{passed}/{total} output comparisons matched",
                data={"passed": passed, "total": total},
            ),
        },
    )
    return row


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-vs"]))
