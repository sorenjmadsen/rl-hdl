# rl-hdl

An **RL-with-verifiable-rewards (RLVR) environment** that teaches an LLM to
generate correct hardware (Verilog/RTL) from a spec. The reward comes from
**real silicon tooling — the Verilator simulator — not an LLM judge**. Hardware
computes the right function or it doesn't, so the grade physically cannot be faked.

See [docs/BRIEF.md](docs/BRIEF.md) for the full project brief, scope, and the
locked design decisions.

## How grading works

The reward seam both the verifier (CPU) and trainer (GPU) build against:

```python
grade(completion: str, task: Task) -> GradeResult(reward: float, info: dict)
```

Each `Task` carries a natural-language spec, an interface, and a **golden
reference** Verilog module. `grade()`:

1. Extracts the candidate module from the model's (often messy) output.
2. Builds a SystemVerilog testbench that instantiates the candidate **and** the
   golden reference, drives the same random input vectors into both, and counts
   matching output comparisons.
3. Compiles everything with `verilator --binary --timing` and runs it.

Reward is correctness-dominant and **dense** (no bare pass/fail):

| Outcome | Reward |
|---|---|
| No extractable module | `0.00` |
| Extracted, won't compile | `0.05` |
| Compiles but sim errors | `0.05` |
| Compiles + runs | `0.10 + 0.90 · (matching comparisons / total)` |

Comparing against a golden reference (rather than hand-authored expected values)
makes the reward dense for free and makes held-out reward-hacking checks trivial:
just reseed the random vectors.

## Tasks

`cologic/tasks.py` ships training tasks, held-out tasks, and converted
verified-gradient tasks:

- **`TRAIN_TASKS`**: mux2, mux4, add4, cmp8, alu8, dec3to8, popcount8, shl8,
  absdiff8, bin2gray8.
- **`HELDOUT_TASKS`**: perturbed variants — widened/narrowed, renamed ports
  and modules, recombined functions, and an inverse (gray→bin). These give
  the **headline** metric: warm-start models may have seen public benchmarks, so
  the gain is measured on structurally novel tasks.
- **`GRADIENT_TASKS`**: tasks distilled from real verified gradients in
  accelerator repos. They cover repeated TPU matrix multiply, signed output
  selection, and an NPU MAC-path integer-to-FP32 conversion bug.

The repo also includes a documented seed mining corpus in
`data/verified_gradients.jsonl`, with reproducible provenance for real-repo RTL
gradients and links from mined gradients to the native `rl-hdl` tasks converted
from them.

Every task's golden reference is smoke-tested to self-grade to `1.0`, which
catches a malformed reference before it can poison training.

## Baseline eval (Modal)

The zero-shot `pass@1` on the held-out split is the floor's headline number and
the demo's red/green source of truth. Both grading **and** inference run in Modal
containers — grading fans out with `.map` (one cached Verilator build), and
Fireworks sampling reads the key from a Modal Secret — so `modal run` works from
any Python env without local deps.

One-time setup of the Fireworks secret:

```bash
modal secret create fireworks-api FIREWORKS_API_KEY=...
```

```bash
# End-to-end check of the Modal grader — no API key, goldens should hit pass@1 = 1.0
modal run modal_app.py::main --selftest --split heldout

# Zero-shot baseline. RLHDL_MODEL picks the Fireworks model / deployment id.
RLHDL_MODEL=accounts/<acct>/deployments/<id> modal run modal_app.py::main --split heldout --n 5
modal run modal_app.py::main --split train --n 1

# List Fireworks models the account can reach
modal run modal_app.py::models --substr coder

# Grading throughput (grades/sec through the parallel grader)
modal run modal_app.py::bench --total 256
```

(`::main` is required because the app has multiple entrypoints — Modal won't
auto-pick one.)

Output is a per-task table (`pass`, `mean_reward`), an aggregate `pass@1`, and a
`baseline.json`. `mean_reward` is the dense signal — watch it move before
`pass@1` does. The same `evaluate()` runs in-process via `cologic.eval` for quick
local iteration without Modal.

## Layout

```
cologic/
  schema.py     # Task + GradeResult (the locked seam)
  extract.py    # robust Verilog module extraction from LLM output
  verifier.py   # grade() — Verilator-grounded dense reward
  tasks.py      # TRAIN_TASKS + HELDOUT_TASKS (+ golden references)
  prompt.py     # Task -> chat messages for the policy model
  inference.py  # Fireworks (OpenAI-compatible) sampling
  eval.py       # pass@1 / mean-reward aggregation (grader-agnostic)
modal_app.py    # Modal image (Verilator) + parallel grader + baseline entrypoint
agents/         # Plan/Forge/Prove self-improvement loop on cologic (see agents/README.md)
tests/
  test_verifier.py
  test_eval.py
docs/
  BRIEF.md      # full project brief
```

## Setup

Requires [Verilator](https://verilator.org) on `PATH` (`brew install verilator`).

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest -q
```

## Decision records

### ADR-001: consolidate the backend into `cologic/`

**Status:** accepted (PR #3). **Date:** 2026-06-20.

**Context.** Two reward engines had grown in parallel: `rl_hdl/` (Verilator,
candidate-vs-golden-reference dense reward, plus task library, Fireworks inference,
Modal parallel grader) and an earlier `cologic/` (iverilog + VCD toggle/power
proxies, a CLI demo over `examples/systolic_array/`). "Cologic" is the product name
(the `web/` visualizer + the `agents/` loop); having it also name a second, weaker
engine was confusing.

**Decision.**
- The Verilator engine (`rl_hdl/`) is canonical and is **renamed to the `cologic/`
  package** — one backend, named after the product.
- The old iverilog/VCD engine, its `tests/test_reward.py`, and the
  `examples/systolic_array/` demo are **removed**. Verilator + golden references are
  the non-lying oracle; the iverilog path was redundant.
- The Exa search spike (`search.mjs`, root `package.json`/`package-lock.json`, the
  `exa-js` dep) is **removed** — scaffolding unrelated to the backend.

**Consequences.**
- Imports are `cologic.*` (was `rl_hdl.*`); the wheel ships `packages = ["cologic"]`.
  The distribution name stays `rl-hdl` (the repo) and the Modal app stays `rl-hdl`.
- **Dropped (revisit when needed):** the VCD-based **power/timing proxies** only the
  old engine had. Re-add as real metrics on top of synthesis (yosys+sky130 for power,
  OpenSTA for timing) rather than as toggle counts.
