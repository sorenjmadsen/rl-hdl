"""Local single-completion baseline: generate RTL via the configured backend
(Fireworks deployment / HUD gateway), grade with local Verilator. No agentic
tools, no HUD runtime tunnel — so it sidesteps the tool-write bug + 504s.

  export $(grep -v '^#' .env.local | xargs)   # RLHDL_MODEL + FIREWORKS_* + key
  python -m cologic.baseline_local [n] [train|heldout]
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from cologic import inference
from cologic.eval import evaluate
from cologic.tasks import HELDOUT_TASKS, TRAIN_TASKS
from cologic.verifier import grade

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
split = sys.argv[2] if len(sys.argv) > 2 else "heldout"
tasks = HELDOUT_TASKS if split == "heldout" else TRAIN_TASKS

print(f"baseline: model={inference.model_id()} split={split} n={n} tasks={len(tasks)}", flush=True)
pairs = inference.sample(tasks, n=n, max_tokens=2048, max_workers=8)


def grade_batch(prs):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda p: asdict(grade(p[1], p[0])), prs))


report = evaluate(pairs, grade_batch, model=inference.model_id())
print(report.table(), flush=True)

# chart-ready JSON (cologic.chart_baseline reads this)
import json
from dataclasses import asdict
out = {"model": inference.model_id(), "split": split, "n": n,
       "pass_at_1": report.pass_at_1, "mean_reward": report.mean_reward,
       "per_task": [{"task_id": t.task_id, "pass_rate": t.pass_rate,
                     "mean_reward": t.mean_reward} for t in report.per_task]}
with open(f".context/hud/baseline_{split}.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"wrote .context/hud/baseline_{split}.json", flush=True)
