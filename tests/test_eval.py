"""Eval-harness logic: pass@1 aggregation, and a golden end-to-end check that
the same machinery the Modal entrypoint uses produces pass@1 = 1.0 on goldens.
"""

import shutil

import pytest

from cologic.eval import evaluate, local_grade_batch
from cologic.prompt import build_user_prompt
from cologic.tasks import BY_ID, HELDOUT_TASKS


def test_prompt_includes_interface():
    task = BY_ID["alu8"]
    p = build_user_prompt(task)
    assert "alu8" in p
    for port in task.interface:
        assert port.name in p


def test_pass_at_1_aggregation_with_fake_grader():
    # Two tasks, n=2 each: task A passes both, task B passes one. pass@1 = 0.75.
    a, b = HELDOUT_TASKS[0], HELDOUT_TASKS[1]
    pairs = [(a, "x"), (a, "x"), (b, "x"), (b, "x")]
    fake = [
        {"reward": 1.0, "info": {"stage": "graded", "passed": 4, "total": 4}, "task_id": a.task_id},
        {"reward": 1.0, "info": {"stage": "graded", "passed": 4, "total": 4}, "task_id": a.task_id},
        {"reward": 1.0, "info": {"stage": "graded", "passed": 4, "total": 4}, "task_id": b.task_id},
        {"reward": 0.5, "info": {"stage": "graded", "passed": 2, "total": 4}, "task_id": b.task_id},
    ]
    report = evaluate(pairs, lambda ps: fake, model="fake")
    assert report.pass_at_1 == pytest.approx(0.75)
    assert len(report.per_task) == 2


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_golden_eval_is_perfect():
    subset = HELDOUT_TASKS[:3]
    pairs = [(t, t.reference_rtl) for t in subset]
    report = evaluate(pairs, local_grade_batch, model="golden")
    assert report.pass_at_1 == pytest.approx(1.0)
    assert report.mean_reward == pytest.approx(1.0)
