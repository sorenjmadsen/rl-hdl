# Fireworks RFT Workflow

Date: 2026-06-21 UTC

This repo's RFT path trains from the same reward seam used by local and Modal grading:

```python
grade(completion: str, task: Task) -> GradeResult
```

## Launch

The launcher assembles `fireworks_rft/`, copies `cologic/`, writes `dataset.jsonl`,
smoke-tests the evaluator with golden RTL, then calls Fireworks Eval Protocol.

```sh
modal run scripts/modal_fireworks_rft.py::launch --dry-run --force \
  --base-model accounts/fireworks/models/qwen3-0p6b \
  --account sorenmadsen \
  --output-model cologic-qwen3-rtl-rft
```

```sh
modal run scripts/modal_fireworks_rft.py::launch --force \
  --base-model accounts/fireworks/models/qwen3-0p6b \
  --account sorenmadsen \
  --output-model cologic-qwen3-rtl-rft
```

The dataset currently contains 16 rows: 10 seed combinational RTL tasks and 6
verified-gradient TPU/NPU tasks.

## Status

```sh
modal run scripts/modal_fireworks_rft.py::status \
  --job-id <job-id> \
  --account sorenmadsen
```

Raw Fireworks payload, including metrics/log URLs when present:

```sh
modal run scripts/modal_fireworks_rft.py::status \
  --job-id <job-id> \
  --account sorenmadsen \
  --raw
```

Cancel helper:

```sh
modal run scripts/modal_fireworks_rft.py::cancel \
  --job-id <job-id> \
  --account sorenmadsen
```

## Evaluation

Self-test the Modal grader with golden references:

```sh
modal run modal_app.py::main --selftest --split gradient \
  --out data/rft_eval_selftest_gradient.json
```

Probe whether a Fireworks model is callable through the account's inference API:

```sh
modal run modal_app.py::probe \
  --models-csv 'accounts/fireworks/models/qwen2p5-coder-7b-instruct,accounts/fireworks/models/qwen3-0p6b'
```

## Deployment

Fireworks LoRA fine-tunes are not serverless-callable. Deploy the completed RFT
model to an on-demand deployment before using it through the inference API. The
Modal helper uses the existing `fireworks-api` Modal secret, so no local
`firectl` login or local Fireworks API key is needed.

List existing deployments:

```sh
modal run scripts/modal_fireworks_deploy.py::list_deployments \
  --account sorenmadsen
```

List compatible deployment shapes for a model:

```sh
modal run scripts/modal_fireworks_deploy.py::list_shapes \
  --account sorenmadsen \
  --model accounts/sorenmadsen/models/cologic-qwen3-rtl-rft-0621b
```

If shape discovery is permission-denied, use the default H100 path below. It has
been validated against this account and remains bounded by one max replica and
zero minimum replicas.

Validate deployment parameters without creating a deployment:

```sh
modal run scripts/modal_fireworks_deploy.py::create \
  --account sorenmadsen \
  --model accounts/sorenmadsen/models/cologic-qwen3-rtl-rft-0621b \
  --deployment-id cologic-qwen3-rft \
  --accelerator-type NVIDIA_H100_80GB \
  --accelerator-count 1 \
  --min-replica-count 0 \
  --max-replica-count 1 \
  --validate-only
```

Create the bounded RFT deployment:

```sh
modal run scripts/modal_fireworks_deploy.py::create \
  --account sorenmadsen \
  --model accounts/sorenmadsen/models/cologic-qwen3-rtl-rft-0621b \
  --deployment-id cologic-qwen3-rft \
  --accelerator-type NVIDIA_H100_80GB \
  --accelerator-count 1 \
  --min-replica-count 0 \
  --max-replica-count 1
```

For a fair before/after eval, also create a bounded deployment for the base:

```sh
modal run scripts/modal_fireworks_deploy.py::create \
  --account sorenmadsen \
  --model accounts/fireworks/models/qwen3-0p6b \
  --deployment-id qwen3-0p6b-base \
  --accelerator-type NVIDIA_H100_80GB \
  --accelerator-count 1 \
  --min-replica-count 0 \
  --max-replica-count 1
```

Probe deployment inference. The probe retries 503/scale-from-zero responses:

```sh
modal run scripts/modal_fireworks_deploy.py::probe \
  --account sorenmadsen \
  --target cologic-qwen3-rft
```

Run a before/after eval once the deployments probe successfully:

```sh
RLHDL_MODEL=accounts/sorenmadsen/deployments/qwen3-0p6b-base \
modal run modal_app.py::main --split heldout --n 1 \
  --out data/rft_eval_base_heldout.json \
  --dump data/rft_eval_base_heldout.jsonl

RLHDL_MODEL=accounts/sorenmadsen/deployments/cologic-qwen3-rft \
modal run modal_app.py::main --split heldout --n 1 \
  --out data/rft_eval_rft_heldout.json \
  --dump data/rft_eval_rft_heldout.jsonl
```

Repeat with `--split gradient` for the TPU/NPU tasks.

## Current Notes

- The earlier Gemma 4 RFT job `p0qwk2j6` failed in the trainer with
  `Model type gemma4 not supported`.
- A Qwen3 job `h8q9sbpg` was accepted by Fireworks RFT, but
  `accounts/fireworks/models/qwen3-0p6b` is not callable through the account's
  public inference endpoint, so standalone before/after eval requires deploying
  the base/output models or enabling inference access.
- Qwen3 job `h8q9sbpg` completed successfully and produced
  `accounts/sorenmadsen/models/cologic-qwen3-rtl-rft-0621b`. Fireworks reported
  128 rollout evaluations with average score `0.04849853125`, compiled average
  `0.0625`, and matched-fraction average `0.0230712890625`.
- The Fireworks API key in Modal can create RFT jobs/evaluators. The account's
  chat inference endpoint currently returns 404 for the probed public base model
  IDs, so base-vs-RFT eval is blocked until a callable/deployed base and output
  model are available.
