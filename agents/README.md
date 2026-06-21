# agents/ — the three-agent self-improvement loop

The product (**Cologic**) shows an agent writing Verilog, watching a reward climb,
and converging on a good design "in real time." This package is that loop, wired
around the existing **rl-hdl** reward seam.

## The three roles (from the Jun 20 design meeting)

They are **tools, not separate models** — effectively one model improving a design
in a loop. Split into three roles so a planner can steer toward a global optimum:

| Role | Job | Backed by |
|------|-----|-----------|
| **Plan** (Claude) | read the spec + last critique → a short fix plan | `Plan` in `loop.py` |
| **Forge** (policy) | write / rewrite the candidate Verilog | `rl_hdl.prompt` + a policy model (Gemma on Fireworks) |
| **Prove** (Verilator) | grade candidate vs golden reference, map outputs → feedback | `rl_hdl.verifier.grade` |

Loop: `Plan → Forge → Prove → feedback → Forge …` keep the best, stop when it hits
`target_reward` or stops improving for `patience` rounds (the "maximum optimal point").

```python
from agents import improve
from rl_hdl.tasks import TRAIN_TASKS

best, history = improve(TRAIN_TASKS[0], forge_model=my_model_fn)
# best.reward, and history[i].reward is the live "watch it get better" curve
```

`forge_model` / `plan_model` / `grader` are injected callables, so the loop runs
offline for testing (`python -m agents.loop` → stub model + stub grader, no API key,
no Verilator) and against the real stack in production.

## cologic vs rl-hdl (they are the same project)

- **rl-hdl** = the repo and the *engine*: the RLVR environment. The canonical
  grader is `rl_hdl/verifier.py` (**Verilator**, golden-reference, dense reward),
  with `tasks.py`, `inference.py`, `eval.py`, and `modal_app.py` (parallel grading).
- **Cologic** = the *product name* — the visualizer (`web/`) + this agent loop that
  sit on top of the engine.
- `cologic/` (the Python dir) is an **earlier, second reward engine** (iverilog +
  VCD toggle/power proxies). It overlaps `rl_hdl/verifier.py`. Verilator is canonical;
  keep `cologic/` only for the power/timing **proxies** rl_hdl doesn't have yet, or
  fold those into rl_hdl and delete it. **Decision needed — see PR #3.**

## Backend APIs needed

The loop needs four things behind it; three already exist in this repo:

1. **Grade** — `grade(completion, task) → {reward, info}`. ✅ `rl_hdl.verifier`
   (local) and `modal_app.py` (parallel, Verilator image). This is the non-lying oracle.
2. **Policy inference (Forge)** — `messages → completion`. ✅ `rl_hdl.inference`
   (Fireworks, OpenAI-compatible). Needs `FIREWORKS_API_KEY`. This serves the
   Gemma policy and, during RL, the model being trained.
3. **Planner inference (Plan)** — `messages → plan`. ⬜ optional Claude/Anthropic
   call; today defaults to a pass-through of Prove's critique. Plug a `model_fn`.
4. **Train / weight-update** — feed `reward` back as the RLVR signal so the policy
   actually improves across episodes (Fireworks RL fine-tune). ⬜ **the missing piece** —
   this turn's loop optimizes *within* one task at inference time; closing the flywheel
   ("agent updates its own weights") is the Fireworks training job.

So the only net-new backend surface beyond what's merged is: **(a)** an optional
Claude planner endpoint and **(b)** the Fireworks RL training/update job that
consumes the `reward` stream. Everything else (grade, inference, parallel eval on
Modal) is already wired.
