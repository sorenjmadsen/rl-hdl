# Cologic Architecture

Last updated: 2026-06-21.

Cologic is an RL-with-verifiable-rewards environment for Verilog/RTL work. The
central bet is simple: hardware tasks can be graded by deterministic EDA tools,
so model improvement can be driven by a reward that is not an LLM judge.

The repo currently supports two related workflows:

1. **Generate RTL from a spec.** A policy writes a module, and Verilator compares
   it against a golden reference over random stimulus.
2. **Optimize existing RTL.** A policy rewrites a correct baseline, Verilator
   gates equivalence, and Yosys ranks equivalent survivors by synthesized cell
   count. Liberty-mapped real area is recorded when available, but the reward
   still uses technology-independent cells.

## System Map

```text
                 specs / baselines / uploads
                             |
                             v
        +---------------- c o l o g i c ----------------+
        |                                                |
        | schema.py        Task, Port, GradeResult       |
        | extract.py       module extraction/renaming    |
        | prompt.py        model-facing chat prompts     |
        | inference.py     Fireworks/OpenAI sampling     |
        | eval.py          pass@1 and mean reward        |
        | rft.py           Eval Protocol JSONL rows      |
        | upload.py        uploaded RTL -> Task          |
        |                                                |
        | verifier.py      generation reward             |
        | grader/          optimization reward           |
        | designs.py       optimization task library     |
        +-------------------------+----------------------+
                                  |
                                  v
        +--------------------- modal_app.py ---------------------+
        | Verilator + Yosys image, Fireworks secrets, parallel   |
        | grade/map functions, baseline eval, optimizer API      |
        +---------------+--------------------+-------------------+
                        |                    |
                        v                    v
              Fireworks RFT           Next/Vercel frontend
              fireworks_rft/          frontend/src/*
              scripts/*               web/ static snapshots
```

The stable seam is:

```python
grade(completion_or_rtl: str, task: Task) -> GradeResult
```

`Task` is the cross-cutting contract. It carries the user-visible spec, required
top module, interface, golden or baseline RTL, vector count, seed, and optional
clocked-testbench metadata. `GradeResult.reward` is always a float in `[0, 1]`;
`GradeResult.info` carries diagnostics used by evals, training logs, repair
loops, and the frontend.

## Generation Grader

`cologic/verifier.py` is the spec-to-RTL grader.

Flow:

1. Extract a candidate Verilog module from messy model output.
2. Rename it to the task's required top module when needed.
3. Rename the reference RTL to `<top>_ref`.
4. Generate or fill a differential SystemVerilog testbench.
5. Compile and run with `verilator --binary --timing`.
6. Parse `RESULT <passed> <total>` and return dense correctness reward.

Reward schedule:

| Stage | Reward |
| --- | ---: |
| No extractable module | `0.00` |
| Compile error | `0.05` |
| Simulation error | `0.05` |
| Compiles and runs | `0.10 + 0.90 * passed / total` |

This path is used by baseline evals, correctness tasks, gradient-derived tasks,
and the Fireworks RFT correctness evaluator.

## Optimization Grader

`cologic/grader/__init__.py` is the optimize-existing-RTL grader.

Flow:

1. Run differential equivalence against `task.reference_rtl` using Verilator.
2. Reject non-equivalent designs before any PPA credit.
3. Synthesize both reference and candidate with Yosys.
4. Compute cell-count improvement:

   ```text
   (ref_cells - cand_cells) / ref_cells
   ```

5. Return:

   ```text
   EQUIV_BASE + ALPHA * improvement
   ```

   clamped to `[EQUIV_FLOOR, 1.0]`.

Important constants:

| Constant | Meaning |
| --- | --- |
| `NO_MODULE_REWARD = 0.00` | No usable candidate |
| `COMPILE_ERROR_REWARD = 0.05` | Syntax/tool failure |
| `NOT_EQUIVALENT_REWARD = 0.10` | Correctness gate failed |
| `EQUIV_BASE = 0.50` | Equivalent, no measured area win |
| `EQUIV_FLOOR = 0.30` | Equivalent but larger still beats wrong |
| `ALPHA = 0.50` | PPA reward weight |

`cologic/grader/ppa.py` provides:

- `synth_cells()` for technology-independent Yosys cell count. This is the live
  optimization reward metric.
- `synth_area_um2()` for liberty-mapped standard-cell area. Modal sets
  `RLHDL_LIBERTY` to a Nangate45 `.lib`; the resulting `*_area_um2` fields are
  observe-only today.

If Yosys is absent, equivalent candidates return `equivalent_no_ppa` with the
equivalence base reward. The Modal image includes Yosys, so production optimize
runs get the full PPA path.

## Task Libraries

`cologic/tasks.py` covers generation/correctness tasks:

- `TRAIN_TASKS`: small combinational seed tasks such as muxes, adders, ALU,
  decoder, popcount, shifter, absdiff, and binary-to-gray.
- `HELDOUT_TASKS`: structurally perturbed tasks used for headline pass@1.
- `GRADIENT_TASKS`: tasks distilled from verified real-repo RTL gradients,
  including TPU and NPU cases.

`cologic/designs.py` covers optimization tasks:

- Curated combinational baselines such as `opt_mul8`, `opt_mux4`,
  `opt_popcount8`, `opt_share_mul`, and held-out `opt_share_add`.
- A clocked TPU matrix-multiply optimization task that reuses a custom
  differential testbench template.

`cologic/datasets/verilogeval.py` loads the bundled VerilogEval combinational
subset for benchmark-style generation tasks.

## Execution

`modal_app.py` is the remote execution boundary. It builds Modal images that
bundle Verilator, Yosys, optional liberty data, OpenAI-compatible sampling
dependencies, and the local `cologic`/`harness` packages.

Key functions and entrypoints:

| Function | Role |
| --- | --- |
| `grade_remote` | Parallel generation grading |
| `grade_opt_remote` | Parallel optimization grading |
| `sample_remote` | Fireworks completions in Modal |
| `main` | Baseline generation eval over train/heldout/gradient splits |
| `floor` | Optimization-grader smoke test on known good/broken rewrites |
| `optimize_remote` | One-shot harness optimization for a design |
| `flywheel_remote` | Multi-generation optimize-until-plateau loop |
| `measure_remote` | Baseline vs zero-shot vs loop comparison |
| `web()` | FastAPI optimizer API for the frontend |

Fireworks credentials are passed through the Modal secret `fireworks-api`.
The web optimizer API can be protected with `rlhdl-web` / `RLHDL_WEB_TOKEN`.

## Harness And Flywheel

`harness/optimizer.py` repurposes a MAGE-style loop for RTL optimization:

1. Seed the candidate pool with the baseline.
2. Sample high-temperature structural rewrites from the policy.
3. Grade every candidate through the immutable optimization grader.
4. Feed failed-but-compiled candidates back through a repair prompt.
5. Return the highest-reward equivalent survivor.

The harness may use model feedback to steer proposals and repairs, but it never
computes reward itself. Reward only comes from `cologic.grader.grade`.

`harness/flywheel.py` wraps that optimizer in a single-design loop:

1. Grade the original baseline.
2. Ask the harness to beat the current best RTL.
3. Adopt a candidate only if it remains equivalent to the original design and
   reduces cell count by at least `min_delta_cells`.
4. Stop after `patience` non-improving generations.

Equivalence always checks against the original baseline, not against the current
best, so functional drift cannot accumulate across generations.

## Training And Evaluation

`cologic/eval.py` is grader-agnostic aggregation. It consumes `(Task, completion)`
pairs and grade-result dictionaries, then reports per-task pass rate, mean reward,
overall pass@1, and overall mean reward.

`cologic/rft.py` writes Eval Protocol JSONL rows for Fireworks RFT. It supports
both correctness tasks and optimization tasks. The evaluator template in
`fireworks_rft/` imports the same reward seam, so training and eval exercise the
same grader contract.

`scripts/modal_fireworks_rft.py` assembles and launches the Fireworks RFT job from
Modal. Related scripts under `scripts/` collect candidates, verify gradients, and
refresh demo/eval artifacts.

## Upload And Frontend Path

`cologic/upload.py` turns user-supplied Verilog into a gradeable `Task`.

For combinational uploads, it parses ANSI module headers to infer the top module
and port interface. For clocked designs, it can wrap a user-provided scaffold
stimulus into a differential testbench template. Multi-file uploads are
concatenated deterministically, and top-module inference validates ambiguous
multi-module designs.

The live frontend lives in `frontend/`:

- `frontend/src/lib/optimizer.ts` submits multipart uploads to
  `https://yc-hack27--rl-hdl-web.modal.run/optimize`, polls `/jobs/{id}`, and
  normalizes the result into baseline cells, best cells, improvement, history,
  and best RTL.
- `frontend/src/lib/data.ts` fetches `/state` for benchmark numbers and falls
  back to a bundled snapshot.
- UI components under `frontend/src/components/` render the benchmark, optimizer,
  foundry, code, and hero surfaces.

The legacy/static demo assets remain under `web/`. The frontend data contract is
documented in `docs/FRONTEND_DATA_CONTRACT.md`.

## HUD Environment

`cologic-verilog/` is a separate HUD v6 chip-design environment, not the main
`cologic` Python package.

It exposes three tracks around the `stream_arb_fifo` module:

| Task | Track | Grader |
| --- | --- | --- |
| `stream-arb-fifo-repair` | RTL repair | Verilator sim, Yosys synthesis/latch checks, lint |
| `stream-arb-fifo-cocotb-dv` | cocotb DV | Golden pass, mutant kill, coverage |
| `stream-arb-fifo-formal` | formal | Bounded SymbiYosys proofs and cover |

The HUD environment uses root-owned hidden grader files under `/donotaccess` and
an unprivileged `agent` user for the shell. It is useful for agent benchmarking
and taskset work, while `cologic/` remains the core reward/training/backend code.

## Data And Artifacts

Important data/artifact locations:

| Path | Contents |
| --- | --- |
| `data/verified_gradients.jsonl` | Mined verified RTL gradients |
| `data/yosys_verified_gradients*.jsonl` | Yosys-filtered gradient candidates |
| `data/*heldout*.json` | Stored held-out eval results |
| `artifacts/sia_run_*` | SIA run context, notes, diffs, log tails |
| `charts/` | Generated benchmark figures |
| `docs/tpu_matmul_optimization/` | Before/after RTL for TPU optimization docs |

## Invariants

- The reward is tool-computed. LLMs may propose, repair, summarize, or choose
  prompts, but they do not score.
- Correctness gates PPA. Wrong circuits never receive area/timing credit.
- Eval and training share the same `Task` and `GradeResult` seam.
- Held-out numbers should come from structurally perturbed tasks, not public
  tasks the base model may have memorized.
- Optimization rewards currently rank on Yosys cell count. Real `um^2` area is
  observed and logged, not yet the reward.
- Uploaded designs are preflighted by grading the reference against itself before
  launching a long optimization job.

## Known Gaps

- Generation reward is correctness-only; power/timing are not part of
  `cologic/verifier.py`.
- Optimization reward has area via cell count, but no real power or timing
  objective yet.
- Liberty-mapped real area is Modal-backed and observe-only.
- Random-vector equivalence is dense and practical, but not exhaustive formal
  equivalence.
- The frontend `/state` benchmark has a bundled snapshot fallback. Treat it as a
  cached display value unless it is refreshed from a real eval artifact.
