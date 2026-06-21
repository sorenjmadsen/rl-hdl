# Verified Gradient Candidates

Investigation date: 2026-06-20

Scope: find real open-source RTL/chip-design commits or merged PRs that can be reconstructed as `base + test FAIL` and `base + test + gold PASS`. I kept the current `rl-hdl` reward seam in mind:

```python
grade(completion: str, task: Task) -> GradeResult
```

Local tool notes:

- `iverilog` 12.0 and Yosys 0.63 are available.
- Verilator is available only when `VERILATOR_ROOT` is unset.
- Modal CLI 1.5.0 is installed and authenticated under profile `yc-hack27`.
- Cocotb tests were run in `/tmp/rlhdl-gradient/venv` with Python 3.12 because the default `python3` is 3.14 and forced a source build of pinned NumPy.
- Modal run for the verified TPU proof: https://modal.com/apps/yc-hack27/main/ap-ndaw4NCj6GEWbl0jSybEfD
- Modal run for the five-candidate Yash/tpu sweep: https://modal.com/apps/yc-hack27/main/ap-MWOFuM9e1T8JrQnCWrhNYN

## Summary

| Verdict | Repo | PR / commit | Why it matters |
| --- | --- | --- | --- |
| verified | `YashKarthik/tpu` | PR #6, `9c579d5e4d316dce739f0074007743c1dc214ab3` | Small TPU/systolic-array gradient: repeated matrix multiply fails before accumulator-clear RTL and passes after. Best immediate conversion target. |
| verified | `YashKarthik/tpu` | commit `b85c1270d8d03bfcd90b9fbf73789b7cb3c2ef63` | Clean PR #8-era gradient: parent passes signed/instruction tests, test-only exposes wrong outputs, gold passes. Strong additional TPU native-task source. |
| verified | `YashKarthik/tpu` | commit `4c2fad9a000ac87c1636c6a923cf577f838af486` | Integrated TPU feeder/control fix: test-only fails and gold passes, but the parent's old test was already failing. Useful lower-confidence repair gradient. |
| verified | `YashKarthik/tpu` | commit `6cffeff0b1fb340a6352761a94b9570414eb1953` | Working systolic-array commit: test-only fails and gold passes, but parent old test was already failing. Useful as source mining, weaker as eval. |
| verified | `YashKarthik/tpu` | commit `f4ea139d6486f242dc2f59183c7bc47d053d06cb` | Early TPU test/RTL repair: test-only times out and gold passes, but parent old test was already failing. Lower-confidence. |
| verified | `vortexgpgpu/vortex` | commits `196c4e5`, `086d26b`, `47edf04`, `4380ad5` | Verilator-reconstructed CP/control-plane compile/interface gradients. Good GPU/accelerator repo story, but weaker than TPU behavioral tasks. |
| gold_still_fails / base_already_passes | `vortexgpgpu/vortex` | TCU/FEDP DRL/TFR/BHF commits | Free Verilator + SoftFloat/HardFloat path is runnable, but the tested tensor/FEDP candidates did not produce gold-pass behavioral gradients. |
| base_already_passes | `YashKarthik/tpu` | PR #5, `291f0b4f9d324f4a58f6d01b6109c7b17661927f` | Test change does not expose a failing behavior on the base; it is a latency/done cleanup, not a correctness gradient. |
| build_broken | `YashKarthik/tpu` | PR #1, PR #3, PR #8 | Test-only reconstruction references files not present in the base. Commit-level mining inside PR #8 is the better route. |
| unsuitable | `YashKarthik/tpu` | PR #2 | No test/harness delta to apply. |
| commercial_only | `Purdue-SoCET/atalla` | PR #190, `905b4aa8bd5519ae8fd498a0b1907a280d866d6a` | Good small RTL/test delta, but intended unit flow is Questa `vlog/vsim`; direct OSS simulator probes fail before useful behavior checking. |
| commercial_only | `Purdue-SoCET/atalla` | PR #109, `785944acf37185cfc0e0823dde0cd847cdacea5c` | Best systolic-array narrative, but it is a huge integration merge and the provided systolic command is `vlog/vsim` only. |
| unsuitable | `kagandikmen/TPU.sv` | PRs #1-#4 / module benches | Strong TPU narrative and Verilator-compilable benches, but the benches do not reliably fail the simulator on mismatches. |
| build_broken | `thousrm/universal_NPU-CNN_accelerator` | commit `1918fc242bb80045734b882f8b93980b89c4f05a` | `tb_find_max_64` gold runs under Verilator, but test-only reconstruction cannot compile because the tested module is introduced with the gold source. |
| unsuitable | `bradgrantham/alice5` | PR #5, PR #18 | PR #5 is assembler-only; PR #18 is a broad sim/driver integration, not a module-level RTL/test gradient. |

## Evaluated: vortexgpgpu/vortex

- Repo: https://github.com/vortexgpgpu/vortex
- PR history screened for merged source+test changes touching unit tests and RTL/source.
- Free tool path: Debian Verilator 5.006, repo `./configure --tooldir=/opt/vortex-tools --osversion=ubuntu/focal`, a small `/opt/vortex-tools/verilator/bin/verilator` shim for the repo's expected tool path, and replacement of unsupported `GENUNNAMED` lint pragmas with `UNOPTFLAT`.
- TCU/FEDP dependency path: `make -C hw config`, `git submodule update --init third_party/softfloat third_party/hardfloat`, `make -C third_party softfloat -j2`.
- Main Modal runs:
  - Initial Vortex harness/probe: https://modal.com/apps/yc-hack27/main/ap-H1ZaZqJ1cMxBSw7a82gfbu
  - TCU DRL batch: https://modal.com/apps/yc-hack27/main/ap-VlUqDeQSkSsMn7TfNSSknP
  - TCU generated-config rerun: https://modal.com/apps/yc-hack27/main/ap-WJYElNOcNxPzH47MZqzCP4
  - TFR batch: https://modal.com/apps/yc-hack27/main/ap-X2Aze4PQnXNYgCum5GYdKx
  - BHF rerun: https://modal.com/apps/yc-hack27/main/ap-Fr9GkyEUfHqq1GJTNgGn1o
  - CP expansion batch: https://modal.com/apps/yc-hack27/main/ap-qkvTBDlN4VBhFT00DI2KD8

Shared CP command:

```sh
./configure --tooldir=/opt/vortex-tools --osversion=ubuntu/focal
make -C hw/unittest/<unit> clean
make -C hw/unittest/<unit> -j2
timeout 120s make -C hw/unittest/<unit> run
```

### Verified: `196c4e56111ec0742492a35c0b6097a1ebb9ca1b`

- Title: `hw/cp: engine retires on resource done, not on arbiter grant`
- Base SHA: `8b4fdc8b1677a1deb3f19f8bd043c1a4f5a48b44`
- Gold SHA: `196c4e56111ec0742492a35c0b6097a1ebb9ca1b`
- Unit: `hw/unittest/cp_engine`
- Test files: `hw/unittest/cp_engine/VX_cp_engine_top.sv`, `hw/unittest/cp_engine/main.cpp`
- Gold RTL files: `hw/rtl/cp/VX_cp_core.sv`, `hw/rtl/cp/VX_cp_engine.sv`
- Phase A: FAIL at build; test-only harness references new `kmu_done_i`, `dma_done_i`, and `dcr_done_i` pins absent from base RTL.
- Phase B: PASS under Verilator.
- Verdict: `verified`, `gradient_kind=compile_or_interface`.

### Verified: `086d26b9f72e72b0cec95ba423da46eaf5dcb662`

- Title: `runtime: strip legacy launch_*/dcr_* from callbacks_t`
- Base SHA: `a43822c053acee193ddaeca8ef71f0efed321067`
- Gold SHA: `086d26b9f72e72b0cec95ba423da46eaf5dcb662`
- Unit: `hw/unittest/cp_axil_regfile`
- Test files: `hw/unittest/cp_axil_regfile/VX_cp_axil_regfile_top.sv`
- Gold RTL files: `hw/rtl/cp/VX_cp_axil_regfile.sv`, `hw/rtl/cp/VX_cp_core.sv`
- Phase A: FAIL at build; test-only top references `last_dcr_rsp` missing from the base.
- Phase B: PASS under Verilator.
- Verdict: `verified`, `gradient_kind=compile_or_interface`.

### Verified: `47edf04ee9bc001d5d2a9745b020b9729d400666`

- Title: `vortex2: timeline events + module/kernel handles + CP event unit`
- Base SHA: `a3b94b5154f4bc8b6b91c6061dc5ba1bd5ad4ef7`
- Gold SHA: `47edf04ee9bc001d5d2a9745b020b9729d400666`
- Unit: `hw/unittest/cp_engine`
- Test files: `hw/unittest/cp_engine/VX_cp_engine_top.sv`, `hw/unittest/cp_engine/main.cpp`
- Gold RTL files: `hw/rtl/cp/VX_cp_core.sv`, `hw/rtl/cp/VX_cp_engine.sv`, `hw/rtl/cp/VX_cp_event_unit.sv`, `hw/rtl/cp/VX_cp_pkg.sv`
- Phase A: FAIL at build; test-only harness references `bid_event` and `event_done_i` pins absent from base `VX_cp_engine`.
- Phase B: PASS under Verilator.
- Verdict: `verified`, `gradient_kind=compile_or_interface`.

### Verified: `4380ad5d726570084d71481d41f15825fba86258`

- Title: `ci: fix XLEN=32/64 regression bring-up + RTL lint-pragma cleanup`
- Base SHA: `0785ef461bcff65b55819c33ba8f9dc16b936d59`
- Gold SHA: `4380ad5d726570084d71481d41f15825fba86258`
- Unit: `hw/unittest/cp_engine`
- Test files: `hw/unittest/cp_engine/VX_cp_engine_top.sv`
- Gold RTL files: `hw/rtl/cp/VX_cp_axil_regfile.sv`, `hw/rtl/cp/VX_cp_core.sv`, `hw/rtl/cp/VX_cp_dma.sv`, `hw/rtl/cp/VX_cp_engine_bid_if.sv`, `hw/rtl/cp/VX_cp_event_unit.sv`, `hw/rtl/cp/VX_cp_gpu_if.sv`, `hw/rtl/cp/VX_cp_if.sv`
- Phase A: FAIL at build; base+test cannot resolve `VX_cp_engine_bid_if`.
- Phase B: PASS under Verilator.
- Verdict: `verified`, `gradient_kind=compile_or_interface`.
- Caveat: lower confidence than the other CP cases because the parent/base original is already build-broken under this exact unit command.

### Not Counted: Vortex TCU/FEDP

I investigated the stronger AI-accelerator narrative in `hw/unittest/tcu_fedp` across DRL, TFR, and BHF commits. The free tool path is viable after generated-config and submodule prep, but no candidate met base+test FAIL and gold PASS:

- `6b722f3f8015740c41c22dc8906245c1112b4ba2`, DRL sparse integer fix: base+test PASS and gold PASS with `CONFIGS='-DTCU_TYPE_DRL -DXLEN=32'` and `OPTS='--fmt=8 --tests=5000 --sparsity=50'`. Verdict: `base_already_passes`.
- `c8d171bc25fd304f8f2e0503f117e4d6537a3a6b`, DRL accumulator sign-extension fix: base+test FAILs at runtime, but gold also FAILs on infinities. Verdict: `gold_still_fails`.
- `b082cdb124723ee7e6176fbd6313d20662b8751e`, TFR FP8 pipeline fix: base+test FAILs, but gold still FAILs under tested FP8 options. Verdict: `gold_still_fails`.
- `d73d3c629d0856fc698954fdcf9e73986ed1a34e`, BHF FP8 unit fix: after required `LATENCY=13`, base+test PASS and gold PASS. Verdict: `base_already_passes`.

Recommendation for Vortex:

- Keep the four CP gradients as additional training data only if compile/interface gradients are acceptable.
- Do not convert Vortex TCU/FEDP into native `rl-hdl` tasks yet; continue mining for a gold-passing behavioral TCU commit only if more Modal budget is available.
- For the RSI story, YashKarthik/tpu still beats Vortex because it provides behavioral TPU/systolic-array gradients instead of interface-only GPU control-plane gradients.

## Verified: YashKarthik/tpu PR #6

- Repo: https://github.com/YashKarthik/tpu
- PR: https://github.com/YashKarthik/tpu/pull/6
- Title: `Allowed repeated matmul`
- Base SHA: `291f0b4f9d324f4a58f6d01b6109c7b17661927f`
- Gold SHA: `9c579d5e4d316dce739f0074007743c1dc214ab3`
- Test files applied for Phase A: `test/test.py`
- Gold RTL files: `src/PE.v`, `src/controller.v`, `src/systolic_array_2x2.v`
- OSS simulator: Icarus Verilog through cocotb

Setup command:

```sh
/opt/homebrew/bin/python3.12 -m venv /tmp/rlhdl-gradient/venv
/tmp/rlhdl-gradient/venv/bin/python -m pip install -r test/requirements.txt
```

Exact test command:

```sh
cd test
VIRTUAL_ENV=/tmp/rlhdl-gradient/venv \
PATH=/tmp/rlhdl-gradient/venv/bin:$PATH \
PYTHONPATH=/tmp/rlhdl-gradient/venv/lib/python3.12/site-packages \
make clean && \
VIRTUAL_ENV=/tmp/rlhdl-gradient/venv \
PATH=/tmp/rlhdl-gradient/venv/bin:$PATH \
PYTHONPATH=/tmp/rlhdl-gradient/venv/lib/python3.12/site-packages \
make && \
! grep failure results.xml
```

Phase A result, base plus only `test/test.py` from PR #6:

- Result: FAIL.
- Failure line: `AssertionError: C[0][0] = 97 != expected 111`.
- Observed second-matmul outputs: `97, 134, 129, 162`.
- Expected second-matmul outputs: `111, 122, 151, 166`.
- The original base tests pass, so the failure is from the new repeated-matmul check.

Phase B result, gold PR #6:

- Result: PASS.
- Observed second-matmul outputs: `111, 122, 151, 166`.
- Cocotb summary: `TESTS=1 PASS=1 FAIL=0 SKIP=0`.

Modal result:

- Command: `modal run scripts/modal_verify_gradients.py`
- Result: `verified`.
- Remote environment: Debian slim, Python 3.12, Icarus Verilog 11.0, cocotb 1.9.2, NumPy 2.1.3.
- Modal confirmed base original passes, base plus test-only patch fails with `C[0][0] = 97 != expected 111`, and gold passes with `111, 122, 151, 166`.

Why this is a clean gradient:

- It is module-level and small.
- Test-only patch compiles against the base.
- Failure is behavioral, not a build artifact.
- Gold source changes are a compact fix: add `clear` through the systolic array and PEs, and clear loaded/accumulated state after output.
- The RSI story is strong: a tiny TPU-like matrix multiply unit learns a recurrent accelerator bug pattern, not a CPU microarchitecture corner.

Native conversion:

- Added native task `vg_tpu_repeated_matmul2x2` under `GRADIENT_TASKS`.
- Preserved `grade(completion: str, task: Task) -> GradeResult`.
- Added a task-specific clocked self-checking Verilator testbench path for `Task.testbench_template`.
- Added `allow_extra_modules` so generated TPU designs can include helper modules such as PEs or systolic arrays.
- Added a regression that a stale-accumulator implementation compiles but receives partial reward.

## Evaluated: YashKarthik/tpu PR #5

- Repo: https://github.com/YashKarthik/tpu
- PR: https://github.com/YashKarthik/tpu/pull/5
- Title: `Optimize Matrix Multiplication Unit`
- Base SHA: `c434ec5751500819eed21ead887a7c48ebdcc0a5`
- Gold SHA: `291f0b4f9d324f4a58f6d01b6109c7b17661927f`
- Test files applied for Phase A: `test/test.py`
- Gold RTL files: `src/controller.v`
- Exact command: same cocotb/Icarus command as PR #6.

Phase A result:

- Result: PASS on base plus test-only patch.
- Cocotb summary: `TESTS=1 PASS=1 FAIL=0 SKIP=0`.

Phase B result:

- Result: PASS on gold.
- Cocotb summary: `TESTS=1 PASS=1 FAIL=0 SKIP=0`.

Verdict: `base_already_passes`.

Notes:

- The PR improves the done/latency behavior, but the added test still checks only matrix output values, which were already correct on the base.
- This is not useful as a correctness RL gradient unless a new test asserts `done` timing.

## Additional Verified: YashKarthik/tpu Commit Sweep

After proving PR #6 end-to-end, I swept merged-history commits reachable from `origin/main` that touched both `test/test.py` and RTL. This found four more commit-level base+test FAIL / gold PASS gradients. One is clean enough to prioritize; three are useful but lower-confidence because the parent was already failing its older test.

Shared command:

```sh
cd test
VIRTUAL_ENV=/tmp/rlhdl-gradient/venv \
PATH=/tmp/rlhdl-gradient/venv/bin:$PATH \
PYTHONPATH=/tmp/rlhdl-gradient/venv/lib/python3.12/site-packages \
make clean && \
VIRTUAL_ENV=/tmp/rlhdl-gradient/venv \
PATH=/tmp/rlhdl-gradient/venv/bin:$PATH \
PYTHONPATH=/tmp/rlhdl-gradient/venv/lib/python3.12/site-packages \
make && \
! grep failure results.xml
```

### Verified: `b85c1270d8d03bfcd90b9fbf73789b7cb3c2ef63`

- Repo: https://github.com/YashKarthik/tpu
- Title: `clean up instructions`
- Base SHA: `649546e265306ada82f2bc3bf1276f04b83ba257`
- Gold SHA: `b85c1270d8d03bfcd90b9fbf73789b7cb3c2ef63`
- Test files: `test/test.py`
- Gold RTL files: `src/control_unit.v`, `src/mmu_feeder.v`, `src/tpu.v`
- Parent/base original: PASS, `TESTS=1 PASS=1 FAIL=0 SKIP=0`.
- Phase A, base plus only `test/test.py`: FAIL, `AssertionError: C[0][1] = 19 != expected 22`; observed first output row/vector collapsed to `19, 19, 19, 19`.
- Phase B, gold: PASS, `TESTS=1 PASS=1 FAIL=0 SKIP=0`; gold also passes signed cases such as `51,-48,71,-68` and `-13,34,31,-18`.

Verdict: `verified`.

Notes:

- This is the best new candidate after PR #6 because the parent's existing test already passes.
- Converted into native task `vg_tpu_signed_outputs2x2`.
- This task covers signed matrix elements and output-select control, matching the observed `C[0][1] = 19 != expected 22` failure shape.

### Verified: `4c2fad9a000ac87c1636c6a923cf577f838af486`

- Repo: https://github.com/YashKarthik/tpu
- Title: `make tests pass, follow yosys guidance`
- Base SHA: `31e0cb79b92b3ebf12d7168c59a67d13c5f79087`
- Gold SHA: `4c2fad9a000ac87c1636c6a923cf577f838af486`
- Test files: `test/test.py`
- Gold RTL files: `src/PE.v`, `src/control_unit.v`, `src/memory.v`, `src/mmu_feeder.v`, `src/tpu.v`
- Parent/base original: FAIL, `AssertionError: C[0][0] = 29 != expected 19`.
- Phase A, base plus only `test/test.py`: FAIL, `AssertionError: C[0][0] = 10 != expected 19`.
- Phase B, gold: PASS, first multiply `19,22,43,50`, second multiply `111,122,151,166`.

Verdict: `verified`.

Notes:

- This satisfies the formal verified-gradient check, but it is weaker as an eval seed because the parent was not clean before applying the new test.

### Verified: `6cffeff0b1fb340a6352761a94b9570414eb1953`

- Repo: https://github.com/YashKarthik/tpu
- Title: `REAL SYSTOLIC ARRAY WORKING!`
- Base SHA: `3697d5d019b37a15ea546ebd25e0d2c4d1afef4f`
- Gold SHA: `6cffeff0b1fb340a6352761a94b9570414eb1953`
- Test files: `test/test.py`
- Gold RTL files: `src/PE.v`, `src/controller.v`, `src/systolic_array_2x2.v`
- Parent/base original: FAIL, timed out waiting for `done`.
- Phase A, base plus only `test/test.py`: FAIL, `AssertionError: C[0][0] = 0 != expected 19`.
- Phase B, gold: PASS, outputs `19,22,43,50`.

Verdict: `verified`.

Notes:

- Good source-mining material for systolic-array structure, but lower-confidence for eval due to failing parent control.

### Verified: `f4ea139d6486f242dc2f59183c7bc47d053d06cb`

- Repo: https://github.com/YashKarthik/tpu
- Title: `the tests work!`
- Base SHA: `05180ed024bbf9a01ee303a0709bd894078933f4`
- Gold SHA: `f4ea139d6486f242dc2f59183c7bc47d053d06cb`
- Test files: `test/test.py`
- Gold RTL files: `src/controller.v`, `src/mmu.v`, `src/tpu.v`
- Parent/base original: FAIL, `AssertionError: assert 00000000 == 50`.
- Phase A, base plus only `test/test.py`: FAIL, `AssertionError: Timed out waiting for 'done' signal`.
- Phase B, gold: PASS, `Matrix multiplication passed.`

Verdict: `verified`.

Notes:

- This is an early repair commit. Keep it below PR #6 and `b85c127` for training/eval conversion.

## Evaluated: YashKarthik/tpu Other PRs

- PR #1: base and test-only builds fail because the test path references files not present in the base, including `project.v` / `src/mmu.v`; gold passes. Verdict: `build_broken`.
- PR #2: no usable test/harness delta. Verdict: `unsuitable`.
- PR #3: test-only build fails because `src/systolic_array_2x2.v` is missing in the base; gold passes. Verdict: `build_broken`.
- PR #8: top-level PR test-only build fails because the new Makefile/source list references `src/mmu_feeder.v` and related files absent from the base. Commit-level mining inside PR #8 produced the verified `4c2fad9` and `b85c127` instances above. Verdict for the PR-level reconstruction: `build_broken`.

## Evaluated: Purdue-SoCET/atalla PR #190

- Repo: https://github.com/Purdue-SoCET/atalla
- PR: https://github.com/Purdue-SoCET/atalla/pull/190
- Title: `wdata_queue fully verified`
- Base SHA: `3a2196529f5092ac49b81f89207e232915eb235b`
- Gold SHA: `905b4aa8bd5519ae8fd498a0b1907a280d866d6a`
- Test files: `tb/unit/ddr_cntrl/testbench/nb_wdata_queue_prop.sv`, `tb/unit/ddr_cntrl/testbench/nb_wdata_queue_tb.sv`
- Gold RTL files: `rtl/include/ddr_cntrl/ddr_controller_if.sv`, `rtl/include/ddr_cntrl/dram_pkg.svh`, `rtl/modules/ddr_cntrl/nb_wdata_queue.sv`, `rtl/modules/ddr_cntrl/nb_wdata_wrapper.sv`

Repo-native command run:

```sh
make test folder=/ddr_cntrl tb_file=nb_wdata_queue_tb.sv GUI=OFF
```

Result:

- Build did not reach simulation: `[test] No .sv under ./rtl/include/ddr_cntrl`.
- The Makefile is a Questa flow using `vlog` and `vsim`.

Direct OSS commands probed:

```sh
unset VERILATOR_ROOT
verilator --binary --timing --assert -Wno-fatal \
  -Irtl/include/ddr_cntrl -Irtl/modules/ddr_cntrl \
  --top-module nb_wdata_queue_tb \
  rtl/include/ddr_cntrl/dram_pkg.svh \
  rtl/include/ddr_cntrl/ddr_controller_if.sv \
  rtl/modules/ddr_cntrl/flex_counter.sv \
  rtl/modules/ddr_cntrl/priority_enc.sv \
  rtl/modules/ddr_cntrl/nb_wdata_queue.sv \
  rtl/modules/ddr_cntrl/nb_wdata_wrapper.sv \
  tb/unit/ddr_cntrl/testbench/nb_wdata_queue_prop.sv \
  tb/unit/ddr_cntrl/testbench/nb_wdata_queue_tb.sv \
  -o nb_wdata_queue_tb_sim
```

```sh
iverilog -g2012 -Irtl/include/ddr_cntrl -Irtl/modules/ddr_cntrl \
  -s nb_wdata_queue_tb -o /tmp/nb_wdata_queue_tb.vvp \
  rtl/include/ddr_cntrl/dram_pkg.svh \
  rtl/include/ddr_cntrl/ddr_controller_if.sv \
  rtl/modules/ddr_cntrl/flex_counter.sv \
  rtl/modules/ddr_cntrl/priority_enc.sv \
  rtl/modules/ddr_cntrl/nb_wdata_queue.sv \
  rtl/modules/ddr_cntrl/nb_wdata_wrapper.sv \
  tb/unit/ddr_cntrl/testbench/nb_wdata_queue_prop.sv \
  tb/unit/ddr_cntrl/testbench/nb_wdata_queue_tb.sv
```

OSS results:

- Verilator fails on `rtl/include/ddr_cntrl/ddr_controller_if.sv:202`: `Modport item not found: 'cg'`.
- Icarus fails parsing interface-style ports in `nb_wdata_queue.sv`.

Verdict: `commercial_only`.

Notes:

- This is a tempting small delta, but it is not currently an OSS-reproducible verified gradient.
- It may become usable if someone writes a small Verilator-compatible wrapper/testbench around `nb_wdata_queue` and avoids the problematic global interface/modport file.

## Evaluated: Purdue-SoCET/atalla PR #109

- Repo: https://github.com/Purdue-SoCET/atalla
- PR: https://github.com/Purdue-SoCET/atalla/pull/109
- Title: `Systolic Array Final`
- Base SHA: `c18b388d0ac5d65fec3c600e5fa9df84e26c1f15`
- Gold SHA: `785944acf37185cfc0e0823dde0cd847cdacea5c`
- Test files: `src/testbench/systolic_array_tb.sv`, `src/testbench/systolic_array_tbint.sv`, `systolic_array_utils/*`
- Gold RTL files: multiple `src/modules/sysarr_*`, `src/modules/systolic_array.sv`, FPU helper changes, and include files.

Command run:

```sh
make -f systolic_array_utils/Makefile sysarr
```

Result:

- Build fails immediately: `/bin/sh: vlog: command not found`.
- The Makefile rule is `vlog -sv ...` followed by `vsim ...`.

Verdict: `commercial_only`.

Notes:

- This is the strongest Atalla RSI narrative, but the PR is a large integration merge with generated outputs, deleted/renamed files, and Questa-only command paths.
- Do not use it as the first training/eval source. At most, mine the final systolic-array code for native task inspiration.

## Evaluated: kagandikmen/TPU.sv

- Repo: https://github.com/kagandikmen/TPU.sv
- Merged PRs inspected: #1 `AXI Wrapper & Improved README`, #2 `Ensure synthesizability; add FPGA help`, #3 `Implement SDK`, #4 docs-only.
- Test files: many `hdl/sim/tb_*.sv` module benches.
- RTL files: `hdl/rtl/*.sv`, `hdl/lib/tpu_pkg.sv`.

Commands probed:

```sh
unset VERILATOR_ROOT
verilator --binary --timing -Wno-fatal \
  --top-module tb_mac_unit \
  hdl/lib/tpu_pkg.sv hdl/rtl/mac_unit.sv hdl/sim/tb_mac_unit.sv
obj_dir/Vtb_mac_unit
```

```sh
iverilog -g2012 -s tb_mac_unit -o /tmp/tpu_sv_tb_mac_unit.vvp \
  hdl/lib/tpu_pkg.sv hdl/rtl/mac_unit.sv hdl/sim/tb_mac_unit.sv
```

Result:

- Icarus fails on package-heavy SystemVerilog syntax in `hdl/lib/tpu_pkg.sv`.
- Verilator compiles `tb_mac_unit` with `-Wno-fatal`, but the bench prints many `Result incorrect` lines and still exits with status 0 after `Tests completed successfully`.
- The only commit found touching both `hdl/sim` and `hdl/rtl` in a direct way was `ae029125aa3b665b7fa566379247213691781ebf`, a repository reorganization moving many files. That is not a clean source/test behavioral gradient.

Verdict: `unsuitable`.

Notes:

- Strong TPU narrative, and the final RTL may be useful for native task inspiration.
- Not currently a verified-gradient source unless the upstream benches are strengthened to use `$fatal`, assertions, or an external pass/fail transcript parser committed as part of the test harness.

## Evaluated: thousrm/universal_NPU-CNN_accelerator

- Repo: https://github.com/thousrm/universal_NPU-CNN_accelerator
- Candidate tried: commit `1918fc242bb80045734b882f8b93980b89c4f05a`, `fix fp32 adder & design find_max`
- Base SHA: `4203d506485aaacec13aa0d92b98e4d36c146f2d`
- Gold SHA: `1918fc242bb80045734b882f8b93980b89c4f05a`
- Test file: `npu_v2/TB/common/tb_find_max_64.sv`
- Gold RTL files: `npu_v2/RTL/common/find_leading_one.sv`, `npu_v2/RTL/common/find_max.sv`, `npu_v2/RTL/common/find_max_4.sv`, `npu_v2/RTL/common/find_max_64.sv`

Command run:

```sh
unset VERILATOR_ROOT
cd npu_v2
verilator --binary --timing -Wno-fatal \
  --top-module tb_find_max_64 \
  RTL/common/find_max_4.sv RTL/common/find_max_64.sv TB/common/tb_find_max_64.sv
timeout 3s obj_dir/Vtb_find_max_64
```

Phase A result:

- Build broken: test-only reconstruction cannot compile on the parent.
- Verilator reports `RTL/common/find_max_4.sv:30:17: syntax error` and cannot find `RTL/common/find_max_64.sv` because the tested module is introduced with the gold source.

Phase B result:

- Gold builds under Verilator and prints `Test Passed` lines for random vectors.
- The bench lacks `$finish`, so the run requires a timeout and transcript parsing.

Verdict: `build_broken`.

Other probe:

- `tb_fp32_adder` builds with dependencies, but latest gold prints many `Random Test ... FAILED` lines and never exits. Not a candidate.

## Evaluated: bradgrantham/alice5

- Repo: https://github.com/bradgrantham/alice5
- Merged PRs inspected: #5 `as: implement rounding mode more fully`, #18 `Move RAM interaction to H2F/F2H`

Results:

- PR #5 touches only `as.cpp`; no RTL/test source seam. Verdict: `unsuitable`.
- PR #18 touches `README.md`, `gpu/sim/Main.v`, `gpu/sim/corecomm.cpp`, `gpu/sim/sim_main.cpp`; this is a broad sim/driver interface change, not a module-level RTL/test gradient.
- The `gpu/sim` and `gpu/fpu_test` Makefiles hardcode `VERILATOR_ROOT=$(HOME)`, which is broken in this environment. Direct invocation with `env -u VERILATOR_ROOT` reaches Verilator, but `gpu/fpu_test` then requires modern `--timing` flags and is unrelated to a merged PR test/source gradient.

Verdict: `unsuitable`.

Notes:

- The GPU story is interesting, but this repo is not competitive with the TPU gradients for immediate `rl-hdl` task conversion.

## Recommendation

Continue sweeping and converting `YashKarthik/tpu`, not Atalla, for immediate verified-gradient work.

The best current path is:

```python
grade(completion: str, task: Task) -> GradeResult
```

Completed so far:

1. Added the minimal clocked harness path to `verifier.py` without changing the public grade signature.
2. Added `Task.clocked=True` TPU/matmul task `vg_tpu_repeated_matmul2x2`.
3. Kept `n_vectors` as scenario count: each scenario runs two independent matrix multiplies to catch stale accumulators.
4. Verified the upstream PR #6 proof locally and on Modal.
5. Found four additional Yash/tpu commit-level verified gradients; `b85c127` is the best new one because its parent already passes.
6. Converted `b85c127` into native task `vg_tpu_signed_outputs2x2` around signed matrix values and output-select control.

Next best work:

1. Keep PR #6 as the headline clean TPU/systolic-array gradient already implemented as `vg_tpu_repeated_matmul2x2`.
2. Use `vg_tpu_signed_outputs2x2` as the second demo task: it comes from a clean-parent verified gradient and exercises signed/control behavior.
3. Treat `4c2fad9`, `6cffeff`, and `f4ea139d` as source-mining or training-only candidates unless you explicitly want repair-commit gradients with failing parent controls.
4. Deprioritize Atalla until someone writes OSS-compatible module harnesses; its best available flows are still Questa-only.
