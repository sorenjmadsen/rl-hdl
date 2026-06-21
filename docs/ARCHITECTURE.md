# Cologic — Architecture & Thesis

The decisions behind Cologic, captured from the founding discussion (Paritosh + Soren).
This is the "why these signals, why this loop" doc; the code in `cologic/` is the start of it.

## Thesis

Frontier models are weak at hardware design. The fix is the same loop that made coding
models strong — **task → eval → reward → train** — applied to chips: an HDL RL environment
with **verifiable rewards**.

We are **not** building a model. We help frontier labs make *their* models better at
hardware design — "fine-tune your model, make it better at this task, fast."

**Wow moment:** AI-generated Verilog that beats human-designed modules on verifiable
metrics — the hardware analog of AI beating humans at code.

## Why HDL

It's easily verifiable. Drive random input vectors at a design and compare its outputs
against a golden reference model. Logic is a deterministic flow of bits — cheap to check,
no ambiguity about "correct."

## Verification philosophy: sim-to-sim, apples-to-apples

Everything runs in **simulation** (on Modal). We **never** compare a simulation against real
silicon — that's apples-to-oranges. Baselines come from open-source designs (e.g.
**Vortex**, an open GPU/RISC-V core), compared in sim under the same conditions as the
agent's output.

## Sim metrics

- **Correctness** — test vectors vs. a golden model (hard gate).
- **Power** — estimated from synthesized logic, **relative** (not absolute mW yet — see
  "Power metric" below).
- **Clock / timing** — relative timing/slack from synthesis.

## Reward design (staged, verifiable)

The #1 pitch talking point — *why these signals*:

1. **Syntax** — does it compile? Broken ≈ 0 reward; fixed = a small reward.
2. **Functional** — does it pass the test cases? (dense random vectors vs. golden output)
3. **Optimization** — power + timing, *once it's correct*.

Verilog domain expertise ("Weezy") informs which signals matter and how to weight them.

**RLVR over SFT** (talking point #2): reinforcement learning with verifiable rewards enables
recursive improvement — a flywheel where an agent continuously evaluates a chip and modifies
it, rather than a one-shot supervised pass.

## Agents

"Proof / Forge / Plan" are **tools, not separate agents** — effectively one agent with
multiple tools. The first milestone is pre-agentic: train the model, compare to a baseline,
show it beats frontier on the task set.

## Stack & sponsors

| Piece          | Role |
|----------------|------|
| **Modal**      | Parallel eval harness — spin up N serverless sandboxes (10k tests in minutes). App image is cached, so the ~30-min cold start amortizes. **The core scaling unlock.** |
| **Fireworks**  | RL fine-tuning + model serving. |
| **Gemma**      | Base model being fine-tuned. Real baseline: **pass@1 = 0.567**. |
| **HUD**        | Thin API/wrapper layer around the env (fetch task → Fireworks → evaluate → Modal → observe). Optional. |
| **Daytona**    | Not used. |

## Task set

~10 Opus-spawned starter tasks: `ho_mux2_w16`, `ho_cmp4`, `ho_popcount16`, `ho_max2`,
`ho_dec2to4`, `ho_gray2bin8`. Expand via VerilogBench / RTLBench / RTL-Eval.

## Map to this repo

`cologic/verifier.py` `grade(completion, task)` implements the **syntax** and **functional**
stages: it extracts the candidate module, builds a Verilator testbench that drives random
vectors into both the candidate and the golden reference, and returns a dense reward in
`[0,1]`. `cologic/tasks.py` holds the task library, `cologic/inference.py` the policy
sampling, `cologic/eval.py` the pass@1 aggregation, and `modal_app.py` fans grading out
across Modal sandboxes. This `grade()` is the single-rollout reward the Fireworks loop calls;
the `agents/` loop and the `web/` visualizer wrap around it. (See ADR-001 in the top-level
README — the earlier iverilog/VCD engine was removed; Verilator is canonical.)

## Power metric — not built yet

`grade()` today scores **correctness only**. There is **no power or timing signal** in the
backend — the old VCD toggle proxy was dropped with the iverilog engine (ADR-001). The
deployed UI label `rel. power · lower better` is therefore **illustrative**: a placeholder
for a metric the backend does not yet produce. Treat any power number in the demo as fake
until the estimator below lands.

**Real estimator (planned, `cologic/power.py`):**

- `yosys` synthesize RTL → map to **sky130** standard cells (`sky130_fd_sc_hd`).
- Pull per-cell switching energy + leakage from the liberty `.lib`.
- `P ≈ Σ(α · E_switch · f) + Σ leakage`, where activity `α` comes from gate-level toggle
  counts (re-add a VCD/SAIF reader, or get activity from Verilator's `--trace`).
- Add `power_mw` to the `info` dict `grade()` already returns.
- The same toolchain (`yosys` / OpenSTA) also yields real **timing** (clock/slack) — the
  second sim metric.

New deps: `yosys` (brew) + the sky130 PDK liberty (open source).

## Backend roadmap

1. `cologic/power.py` — yosys + sky130 mW + timing. Makes the headline metric real (today
   it's illustrative).
2. Expand the task library in `cologic/tasks.py` (the `ho_*` set above) as more
   DUT + golden-reference pairs.
3. Scale grading on Modal — `modal_app.py` already fans `grade()` across sandboxes; wire its
   per-task pass/reward into the benchmark figure to replace illustrative numbers.
4. Fireworks RLVR loop — serve Gemma, feed `reward` as the training signal; log pass@1 per
   epoch. This is the missing flywheel: the loop in `agents/` improves a design at inference
   time; training closes it.
5. (Optional) thin HUD wrapper as the task API.
