# Demo Runbook

Use this path for the hackathon demo. It shows the system working without
claiming the first tiny RFT run improved model quality.

## Positioning

One sentence:

> We built an RL-with-verifiable-rewards environment for RTL where the reward is
> computed by real silicon tools, not an LLM judge.

What is demo-ready:

- Verilator dense reward for spec-to-RTL generation.
- Yosys PPA reward for equivalent-but-smaller RTL optimization.
- Modal parallel grading.
- Fireworks inference, RFT job completion, and deployed RFT model endpoint.
- Verified TPU/NPU task split with golden selftest.
- Single-design flywheel that rides a design's gate count down until plateau.
- Real externally-authored TPU matmul RTL where the loop beats a zero-shot sample.

Do not claim:

- The first tiny RFT policy is better than its base model. It is deployed and
  callable, but its heldout score is poor.

## Preflight

Run this first:

```sh
uv run python scripts/demo_check.py
```

Expected: all core checks pass, with one explicit warning that the tiny RFT
heldout score is intentionally not the headline.

## Live Commands

Run these serially to avoid Modal app-creation rate limits.

### 1. Headline TPU Optimization Gap

```sh
modal run modal_app.py::measure_run
```

What to point at:

- This is real `tt_um_tpu` RTL from `YashKarthik/tpu`, not a toy authored for
  the demo.
- The same policy is measured two ways: one greedy zero-shot sample vs. the
  search-and-verify loop.
- The only judge is Verilator equivalence plus Yosys cell count.

Recent result:

```text
baseline    1460 cells    equivalent
zero-shot   1460 cells    equivalent
full-loop    452 cells    equivalent
gap: +1008 cells saved by the loop beyond zero-shot
```

Backup artifact: [docs/tpu_matmul_optimization/README.md](tpu_matmul_optimization/README.md)

### 2. Reward Floor

```sh
modal run modal_app.py::floor
```

What to point at:

- Baseline is equivalent.
- `good (a*b)` is still equivalent and gets a better PPA reward.
- `broken` is rejected by the equivalence gate.

Recent result:

```text
baseline       reward 0.500  equivalent True   ref 366  cand 366
good (a*b)     reward 0.516  equivalent True   ref 366  cand 354
broken         reward 0.100  equivalent False
```

### 3. Real Optimization Headroom

```sh
modal run modal_app.py::headroom
```

What to point at:

- These are post-Yosys synthesis savings, not cosmetic text rewrites.
- This motivates the optimization/flywheel route.

Recent result:

```text
share_mul    726 -> 370 cells  +49.0%
share_add    212 -> 130 cells  +38.7%
redundant     82 ->  40 cells  +51.2%
```

### 4. Accelerator Task Selftest

```sh
modal run modal_app.py::main --selftest --split gradient \
  --out data/demo_selftest_gradient.json
```

What to point at:

- All TPU/NPU verified-gradient tasks self-grade to 1.0.
- This is the AI-accelerator story: TPU systolic-array and NPU datapath tasks.

Recent result:

```text
pass@1 1.000   mean 1.000
```

### 5. Fireworks Inference Baseline

```sh
RLHDL_MODEL=accounts/fireworks/models/kimi-k2p7-code \
modal run modal_app.py::main --split heldout --n 1 --max-tokens 1024 \
  --out data/fireworks_inference_kimi_heldout.json \
  --dump data/fireworks_inference_kimi_heldout.jsonl
```

What to point at:

- The same grading path evaluates a live Fireworks policy.
- Recent run passed all six heldout tasks.

Recent result:

```text
pass@1 1.000   mean 1.000
```

### 6. Deployed RFT Endpoint

```sh
modal run scripts/modal_fireworks_deploy.py::probe \
  --account sorenmadsen \
  --target cologic-qwen3-rft \
  --wait-seconds 120 \
  --poll-seconds 15
```

What to point at:

- The RFT job completed, produced a model artifact, and that artifact is deployed.
- The endpoint is live and callable through the OpenAI-compatible API.

Recent result:

```text
ok: true
model: accounts/sorenmadsen/deployments/cologic-qwen3-rft
```

## Backup Lines

If the live internet path stalls:

- Use the recorded artifacts under `data/`.
- Run `uv run python scripts/demo_check.py` locally.
- The core thesis does not depend on the first tiny RFT model being strong; the
  demo is the verified environment and live reward mechanism.

## Honest Status Of RFT

The first RFT job was intentionally tiny. It completed and deployed, but the
heldout eval currently shows:

```text
pass@1 0.000   mean 0.061
```

Frame it as:

> The training/deployment plumbing works end to end. The next iteration is data
> quality and model selection, not reward trust.
