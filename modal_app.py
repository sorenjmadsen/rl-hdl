"""Modal app: parallel Verilator grading + the baseline eval entrypoint.

Grading runs in Modal containers (one Verilator build, fanned out with .map),
so rollouts/sec scales with container count rather than local cores. Inference
(Fireworks) runs locally in the entrypoint and is just concurrent HTTP.

Usage:
  modal run modal_app.py --selftest            # no API key; goldens -> pass@1 = 1.0
  modal run modal_app.py --split heldout --n 5 # zero-shot baseline (needs FIREWORKS_API_KEY)
  modal run modal_app.py --split train  --n 1
"""

from __future__ import annotations

from pathlib import Path

import modal

VERILATOR_TAG = "v5.038"

grader_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git", "make", "g++", "autoconf", "flex", "bison",
        "help2man", "libfl-dev", "ccache", "perl",
    )
    .run_commands(
        f"git clone --depth 1 --branch {VERILATOR_TAG} "
        "https://github.com/verilator/verilator.git /tmp/verilator",
        "cd /tmp/verilator && autoconf && ./configure && "
        "make -j$(nproc) && make install && rm -rf /tmp/verilator",
    )
    .add_local_python_source("rl_hdl")
)

app = modal.App("rl-hdl")


@app.function(image=grader_image, timeout=180)
def grade_remote(completion: str, task) -> dict:
    """Grade one (completion, task) in a container. Task pickles via rl_hdl."""
    from rl_hdl.verifier import grade

    r = grade(completion, task)
    return {"reward": r.reward, "info": r.info, "task_id": task.task_id}


@app.local_entrypoint()
def main(split: str = "heldout", n: int = 1, selftest: bool = False, out: str = "baseline.json"):
    from rl_hdl.eval import evaluate
    from rl_hdl.tasks import HELDOUT_TASKS, TRAIN_TASKS

    tasks = {"heldout": HELDOUT_TASKS, "train": TRAIN_TASKS}[split]

    if selftest:
        # Feed each task its own golden reference: a green end-to-end check of the
        # Modal grader with no model / API key required (expect pass@1 = 1.0).
        pairs = [(t, t.reference_rtl) for t in tasks]
        model = "selftest-golden"
    else:
        from rl_hdl.inference import model_id, sample

        model = model_id()
        print(f"sampling n={n} from {model} for {len(tasks)} {split} tasks ...")
        pairs = sample(tasks, n)

    def modal_grade_batch(ps):
        comps = [c for _, c in ps]
        tks = [t for t, _ in ps]
        return list(grade_remote.map(comps, tks))

    report = evaluate(pairs, modal_grade_batch, model=model)
    print("\n" + report.table() + "\n")
    Path(out).write_text(report.to_json())
    print(f"wrote {out}")
