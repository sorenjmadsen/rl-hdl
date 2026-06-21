# Real silicon area (µm²) — observe-only integration

**Status:** shipped, **observe-only**. The reward still ranks on technology-independent
gate count; real area in µm² is computed and logged alongside it but does **not** affect
any reward yet. This doc is the pick-it-up-later reference: what it is, where it lives,
how to verify it, and exactly how to flip the reward to µm² when we decide to.

## Why this exists

Our reward optimizes for *gate count* from a generic, technology-independent Yosys
`synth -flatten`. That's real and un-fakeable, but it's a **proxy** for area, not silicon
area: all cells are weighted equally, while real standard cells differ wildly in size. A
cell-count win can be area-neutral (or worse) once mapped to a real library.

This integration adds **real area in µm²** by mapping the (same) synthesized structure to
an open standard-cell library and reading `stat -liberty`. It's the credible, hardware-team
number — and the same liberty flow is the prerequisite for timing and (static) power later.

We landed it **observe-only first** on purpose: validate the µm² numbers on Modal before
letting the self-improving loop chase them. A bad/unstable reward would corrupt SIA.

## How the measurement works

`synth_area_um2()` uses the **same** `synth -flatten` front-end as the cell-count path (so
the structure measured is identical), then technology-maps and reports area:

```
read_verilog -sv design.sv
synth -flatten -top <top>
dfflibmap -liberty <lib>     # sequential cells -> library FFs
abc -liberty <lib>           # combinational cells -> library gates
stat -liberty <lib>          # -> "Chip area for module ...: <um^2>"
```

It runs **only on equivalent survivors** (behind the equivalence gate), same as the
existing PPA stage. It is wrapped so any tool/parse failure is swallowed — real-area
measurement can never affect the reward or crash a grade.

## Liberty library

- Default: **Nangate45** (`NangateOpenCellLibrary_typical.lib`), a single self-contained
  `.lib`, fetched into `/opt/pdk/` in the Modal images.
- The grader finds it via the **`RLHDL_LIBERTY`** env var. If unset or the file is missing,
  µm² measurement is skipped (fields stay `None`) — so local dev and the current reward are
  completely unaffected.
- **To swap to Sky130** (more credible PDK, heavier): change the download URL + path in the
  two Modal images and point `RLHDL_LIBERTY` at it. No code change — the grader only reads
  the env var.

## Where it lives (file map)

**Measurement — `cologic/grader/ppa.py`**
- `liberty_path()` — resolves `RLHDL_LIBERTY` (returns `None` if unset/missing).
- `synth_area_um2(rtl, top, *, liberty, timeout)` → `LibertyArea(area_um2, log)`; raises
  `YosysUnavailable` / `RuntimeError`.
- `_chip_area_from_stat()` + `_CHIP_AREA_RE` — parse the `Chip area for [top] module …` line.

**Grader plumbing — `cologic/grader/__init__.py`**
- New `info` keys (stable contract, default `None`): `ref_area_um2`, `cand_area_um2`,
  `area_um2_improvement`.
- Populated only in the `graded` branch, only when `liberty_path()` is set, inside a
  `try/except` that never touches the reward. **Reward math is unchanged.**

**SIA signal — `sia_task/rtl-optimize/data/public/evaluate.py`**
- Per-design dicts carry the three `*_um2` keys.
- New top-level scalar **`mean_area_um2_improvement`** (observe-only). `mean_reward` remains
  the optimization target.

**Harness dataclasses (so the metric reaches the demo tables)**
- `harness/flywheel.py`: `Generation.area_um2`; `FlywheelResult.baseline_area_um2` /
  `.best_area_um2` / `.total_area_um2_improvement`. `run_flywheel` tracks area alongside
  cells (improvement decision still rides on cells).
- `harness/measure.py`: `Arm.area_um2` + `area_um2_improvement_over()`;
  `GapResult.baseline_area_um2`; `format_gap` prints `um²` / `um² base` columns.

**Demo surfaces — `modal_app.py`**
- `_SURFACED_INFO_KEYS` — single list of `info` keys threaded into every JSON dump.
  **This is the one place to edit if the contract changes.**
- `_pct()` / `_area()` formatting helpers.
- µm² columns in the floor, harness, and flywheel tables; measure uses `format_gap`.
- Modal images (`modal_app.py` `_toolchain`, `scripts/modal_rtl_toolchain.py`
  `RTL_TOOLCHAIN_IMAGE`): fetch the liberty file + set `RLHDL_LIBERTY`.

**Tests — `tests/test_grader.py`**
- Area-parser tests, `liberty_path` resolution, a contract test proving the `*_um2` keys are
  present-and-`None` (reward ≥ `EQUIV_BASE`) without a liberty file, and a yosys+liberty
  integration test (skipped unless both are present → runs on Modal).

## How to verify (only runs on Modal)

There is **no yosys or liberty file locally**, so µm² is blank in local runs by design.
On Modal:

```
modal run modal_app.py::measure_run        # gap table should show populated um² columns
# or any grading job; check results.json for ref_area_um2 / cand_area_um2
```

- µm² columns **populated** → working.
- **Blank on Modal** → the liberty download failed at image build (degrades safely: reward
  unaffected). Check the `curl` step in the image and the `RLHDL_LIBERTY` path.
- **Blank locally** → expected (no yosys/lib).

## How to flip the reward to µm² (when ready)

Currently localized — everything that logs/displays µm² is already wired, so the flip is
small:

1. **`cologic/grader/__init__.py:grade()`** — compute `improvement` from area instead of
   cells. Today:
   ```python
   improvement = (ref.cells - cand.cells) / ref.cells if ref.cells else 0.0
   ```
   To flip, base `improvement` on `cand_area_um2` / `ref_area_um2` (which you already compute
   in the observe-only block — move that block above the reward calc, or fold the two synth
   passes together). Keep a graceful fallback to cells when no liberty is configured so local
   dev still produces a reward.
2. **`harness/flywheel.py:run_flywheel()`** — optionally change the `improved` gate from
   `cells <= best_cells - min_delta` to an area-based delta, so the loop adopts on real area.
3. Re-baseline expectations in `tests/test_grader.py` / `test_tpu_opt.py` (reward values will
   change), and re-run the headline gap on Modal.

Until then, **do not** change the reward — the whole point of the observe-only stage is to
trust the µm² numbers first.

## Known gaps / deliberately out of scope

- **Dynamic power** is *not* included. It needs switching activity from a gate-level sim, and
  our equivalence vectors are random (not a representative workload) — a power reward measured
  under them would be precise but meaningless, and would let SIA reward-hack. Prerequisite:
  per-design representative stimulus (same blocker as clock-cycle metrics). See `ARCHITECTURE.md`.
- **Static (leakage) power** is nearly free with the liberty flow (`stat -liberty` reports it)
  but is heavily correlated with area, so low marginal value. Not wired yet.
- **Timing** (critical-path delay) is a rough `abc` estimate from the same flow; real STA needs
  OpenSTA, which is not in the image. Not wired yet.
