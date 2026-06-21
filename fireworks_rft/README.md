# Fireworks RFT

This directory is the Eval Protocol evaluator template for Fireworks
reinforcement fine-tuning. The Modal launcher assembles a temporary upload
directory containing this template plus `cologic/`, writes `dataset.jsonl`, smoke
tests the evaluator with golden RTL, and then calls:

```bash
eval-protocol create rft --base-model ... --output-model ...
```

Run from the repo root:

```bash
# Verify the evaluator path in Modal without launching a paid/long-running RFT job.
modal run scripts/modal_fireworks_rft.py::launch --dry-run

# Launch a tiny supported RFT job. The Fireworks key comes from Modal secret fireworks-api.
modal run scripts/modal_fireworks_rft.py::launch \
  --base-model accounts/fireworks/models/qwen3-0p6b \
  --account <fireworks-account> \
  --output-model cologic-qwen3-rtl-rft
```

The reward function in `test_cologic_reward.py` is still the locked project seam:

```python
grade(completion: str, task: Task) -> GradeResult
```
