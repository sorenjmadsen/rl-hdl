# Handoff — self-improving RTL optimizer

State as of 2026-06-21. Read this to continue in a fresh conversation.

## One line
A self-improving **RTL optimizer**: takes correct Verilog and makes it smaller
(fewer gates), where the **only** thing in the reward path is silicon tooling —
Verilator (equivalence) + Yosys (gate count), **no LLM judge**. Three layers
(grader → harness → self-improvement), all graded by one immutable grader.

## Architecture & where each layer stands

```
Layer 1  IMMUTABLE GRADER     cologic/grader/  — Verilator equiv + Yosys PPA   ✅ done
Layer 2  HARNESS (optimizer)  harness/         — MAGE-style multi-candidate    ✅ done
           + single-design flywheel (run-to-plateau)                           ✅ done
Layer 3a HARNESS LEVER (SIA)  sia_task/ + scripts/modal_sia_run.py             ✅ loop turns
Layer 3b WEIGHT LEVER (RFT)   fireworks_rft/ + scripts/modal_fireworks_rft.py  ⚠️ dry-run only
           (ES-over-LoRA was the brief's pick; we adopted Fireworks RFT instead)
```

The grader is the only reward authority and lives outside everything the system
mutates. SIA evolves the harness scaffold; it cannot touch the grader.

## What works (and the command for each)

First: `modal deploy modal_app.py` (publishes `grade_opt_remote`, the verifier the
SIA agent + evaluate.py call by name). Secrets needed: `fireworks-api`,
`anthropic-api`.

- **Grader floor** — `modal run modal_app.py::floor` (gate-then-climb on mul8).
- **Harness on one design** — `modal run modal_app.py::harness_run --design share_mul`.
- **Flywheel (run to plateau)** — `modal run modal_app.py::flywheel_run --design share_mul`.
- **Headroom probe** — `modal run modal_app.py::headroom`.
- **Loop-vs-zero-shot gap on REAL TPU RTL** — `modal run modal_app.py::measure_run`
  → baseline 1460 → **−69% (452 cells)**, provably equivalent. Best real result. (PR #16)
- **SIA harness-lever loop** — `modal run scripts/modal_sia_run.py::main --max-gen 2`
  (Claude meta + Kimi target). `::seed` runs harness+verifier without the meta-agent;
  `::validate_entry` is a cheap preflight. Evidence: `artifacts/sia_run_12/`.
- **RFT (optimize objective), dry-run** —
  `modal run scripts/modal_fireworks_rft.py::launch --objective optimize --dry-run`.

## Key facts & gotchas (hard-won)

- **Headroom lives in arithmetic, not boolean logic.** Yosys default `synth`
  minimizes boolean logic (abc) but does NOT share arithmetic operators or
  collapse redundant `$mul`/`$add`. So real synth-surviving wins are
  resource-sharing / redundant-arithmetic (share_mul +49%, TPU −69%). Combinational
  boolean rewrites win ~0. `modal run modal_app.py::headroom` quantifies this.
- **Clocked designs** are graded via a per-task `Task.testbench_template` (a
  testbench that drives clk/reset/stimulus into candidate + reference and compares
  over cycles). See `tpu_matmul` in `cologic/designs.py`. This is also the
  mechanism for a user-uploaded test suite.
- **Target model** = `accounts/fireworks/models/kimi-k2p7-code` (serverless,
  always-on). **Meta/feedback** = **Claude** (Agent SDK, `sonnet`). Fireworks-meta
  is a DEAD END: pydantic-ai loops to the turn limit on every model; openhands-ai
  has an unresolvable e2b conflict; openhands-sdk needs py3.12.
- **SIA Modal specifics:** image is toolchain-free (verification = deployed
  `grade_opt_remote` via `modal.Function.from_name`). Needs Node + the
  `@anthropic-ai/claude-code` CLI and `IS_SANDBOX=1` (the SDK runs
  `--dangerously-skip-permissions`, refused as root). Invoke SIA as
  `python -c "from sia.orchestrator import main; main()"`. `SIA_MAX_TURNS` raises
  the 20-turn cap. `cologic` enters SIA's per-gen venv via requirements `-e <repo>`.
- **The guardrail works (demonstrated live).** In run_11 SIA's feedback agent
  rewrote the harness to grade itself with an LLM (Goodhart). The immutable
  `evaluate.py` kept the official score honest. We hardened `task.md` to mandate
  the deployed verifier; run_12 = 9 `[SIM]` / 0 `[BLIND]`. See `artifacts/sia_run_12/`.

## What's next (prioritized)

1. **Wire the TPU (clocked) design into the SIA / upload flow.** Biggest payoff:
   the impressive −69% result is on `tpu_matmul`, but the SIA task package only
   handles combinational designs — `task_from_rtl` parses the interface but does
   not thread a `testbench_template`. Carry it through the manifest so the SIA loop
   optimizes the real TPU. Headline goes from +28% (toy) to −69% (real silicon),
   and it closes the upload-test-suite question.
2. **Held-out generalization eval.** SIA scores on the 4 train designs. Run the
   evolved/promoted harness on `data/private` (`share_add`) for the §10
   train-vs-held-out gap — the reward-hacking guard number.
3. **RFT weight lever — base-model fix.** `scripts/modal_fireworks_rft.py` is wired
   to the optimize reward but only dry-run validated. Gemma isn't fine-tunable on
   Fireworks; switch `--base-model` to a supported one (Qwen 2.5/3, e.g.
   `accounts/fireworks/models/qwen2p5-coder-7b-instruct`) and do a real validation
   (drop `--dry-run`, validation on) before a paid run.
4. **Promotion step.** After a SIA run, snapshot the best generation's
   `target_agent.py` back into the repo (gated, not auto) so harness gains can
   compound across runs.
5. **ES-over-LoRA** (the brief's original weight lever) remains unbuilt; deprioritized
   in favor of RFT. Crib from `VsonicV/es-at-scale` if revisited.

## Pointers
- Evidence: `artifacts/sia_run_12/` (SIA run + guardrail story), `docs/tpu_matmul_optimization/` (before/after RTL).
- Brief: `README.md` build brief; `docs/BRIEF.md`; `docs/demo_runbook.md` (presentation path).
- Seam/ownership: grader + task curation = the verifier owner; training/infra (Modal, SIA, RFT) = Soren.
