# TPU matmul optimization — loop vs. zero-shot (verified)

The optimizer flywheel applied to **real, externally-authored RTL**: `tt_um_tpu`, a
2×2 signed matrix-multiply accelerator from the open-source repo
[`YashKarthik/tpu`](https://github.com/YashKarthik/tpu) (a verified gradient;
provenance in `data/verified_gradients.jsonl`). We did **not** write this design,
and we did **not** supply the optimized answer — the only judge is the immutable
grader (Verilator equivalence + Yosys gate count).

## Result

| arm | what it is | cells | vs baseline | equivalent |
|---|---|---:|---:|:---:|
| baseline | the real `tt_um_tpu`, synthesized as-is | 1460 | — | yes |
| zero-shot | one greedy LLM sample (n=1, no repair, temp 0) | 1460 | +0.0% | yes |
| **full-loop** | the flywheel to plateau (8 cand × ≤8 gens + repair) | **452** | **−69.0%** | **yes** |

**Gap: 1008 cells** saved by the search-and-verify loop beyond a single zero-shot
sample. The bare model improved nothing; the loop found a provably-equivalent
design 69% smaller. Equivalence is 512/512 random clocked I/O vectors against the
original.

> Honest caveat: zero-shot is a single greedy sample; the loop is multi-candidate +
> multi-generation + repair. The claim is "search-and-verify beats the bare model's
> one shot" — the model can reach this design, but only with the loop driving it.
> This run is **only the harness lever** (`harness/flywheel.py` + `harness/optimizer.py`)
> with frozen policy weights and a frozen scaffold — no SIA (scaffold evolution),
> no ES (weight updates). Those remain upside on top.

## The optimization

Only one matrix element leaves the chip per cycle (`output_sel` picks it), so all
four products never need to exist at once. The loop muxes the operands *before*
multiplying and computes only the selected output:

- **before** (`before.v`): `c00..c11` spelled out → **8 multipliers + 4 adders**, then a 4-way output mux.
- **after** (`after.v`): select operands by `output_sel`, then **2 multipliers + 1 adder**.

Register load/reset logic is identical between the two; only the arithmetic
datapath changed. Yosys's default `synth` does not perform this sharing on its own.

## Files

- `before.v` — the baseline (verbatim from `cologic.designs.TPU_MATMUL_BASELINE`).
- `after.v` — the loop's winning rewrite (graded `equivalent`, 512/512 vectors).

## Reproduce

```bash
# real run (Fireworks policy + Yosys, in Modal):
modal run modal_app.py::measure_run

# check the artifact locally against the oracle (Verilator; Yosys adds the cell count):
python -c "from cologic.designs import tpu_matmul; from cologic.grader import grade; \
print(grade(open('docs/tpu_matmul_optimization/after.v').read(), tpu_matmul).info)"
```
