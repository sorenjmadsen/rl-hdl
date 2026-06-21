# agents/ — the three-agent self-improvement loop

The product (**Cologic**) shows an agent writing Verilog, watching a reward climb,
and converging on a good design "in real time." This package is that loop, wired
around the **`cologic/`** backend (the RLVR engine — Verilator grader, task
library, Fireworks inference).

## The three roles (from the Jun 20 design meeting)

They are **tools, not separate models** — effectively one model improving a design
in a loop. Split into three roles so a planner can steer toward a global optimum:

| Role | Job | Backed by |
|------|-----|-----------|
| **Plan** (Claude) | read the spec + last critique → a short fix plan | `Plan` in `loop.py` |
| **Forge** (policy) | write / rewrite the candidate Verilog | `cologic.prompt` + a policy model (Gemma on Fireworks) |
| **Prove** (Verilator) | grade candidate vs golden reference, map outputs → feedback | `cologic.verifier.grade` |

Loop: `Plan → Forge → Prove → feedback → Forge …` keep the best, stop when it hits
`target_reward` or stops improving for `patience` rounds (the "maximum optimal point").

```python
from agents import improve
from cologic.tasks import TRAIN_TASKS

best, history = improve(TRAIN_TASKS[0], forge_model=my_model_fn)
# best.reward, and history[i].reward is the live "watch it get better" curve
```

`forge_model` / `plan_model` / `grader` are injected callables, so the loop runs
offline for testing (`python -m agents.loop` → stub model + stub grader, no API key,
no Verilator) and against the real stack in production.

## cologic = the backend (one engine now)

`cologic/` **is** the RLVR engine. It was `rl_hdl/`; we consolidated under the
product name (see the ADR in the top-level `README.md`). The earlier iverilog/VCD
reward engine was dropped — Verilator is the canonical grader. `Cologic` the product
= this `cologic/` backend + the `web/` visualizer + this agent loop.

## Backend APIs needed

The loop needs four things behind it; three already exist in this repo:

1. **Grade** — `grade(completion, task) → {reward, info}`. ✅ `cologic.verifier`
   (local) and `modal_app.py` (parallel, Verilator image). This is the non-lying oracle.
2. **Policy inference (Forge)** — `messages → completion`. ✅ `cologic.inference`
   (Fireworks, OpenAI-compatible). Needs `FIREWORKS_API_KEY`. This serves the
   Gemma policy and, during RL, the model being trained.
3. **Planner inference (Plan)** — `messages → plan`. ⬜ optional Claude/Anthropic
   call; today defaults to a pass-through of Prove's critique. Plug a `model_fn`.
4. **Train / weight-update** — feed `reward` back as the RLVR signal so the policy
   actually improves across episodes (Fireworks RL fine-tune). ✅
   `scripts/modal_fireworks_rft.py` assembles an Eval Protocol evaluator around
   `grade()`, smoke-tests it in Modal, and launches Fireworks RFT.

So the only net-new backend surface beyond what's merged is an optional Claude
planner endpoint. The weight-update path is now wired through Fireworks RFT; the
remaining work is to scale the task corpus and compare before/after held-out
reward curves.
