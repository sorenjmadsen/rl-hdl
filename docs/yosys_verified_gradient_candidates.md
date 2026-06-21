# Yosys Verified Gradient Sweep

Run date: 2026-06-20 PDT

Scope: merged RTL/source PRs from the candidate repos, swept with generated Yosys rewards on Modal. This is separate from the behavioral Verilator/cocotb report in `docs/verified_gradient_candidates.md`.

The reward seam remains:

```python
grade(completion: str, task: Task) -> GradeResult
```

## Reward Semantics

- `yosys_synth`: the base side fails the generated Yosys synthesis/check reward, or the changed RTL file is absent from the base, while the gold side parses/synthesizes/checks under Yosys.
- `yosys_equiv`: base and gold both synthesize, then a generated Yosys miter/equivalence check fails for base against gold while the gold side still passes synthesis/check.
- `test-backed`: the PR also touched a test/harness path. This is stronger than a pure source-only Yosys reward, but still not the same as an end-to-end behavioral testbench pass.

Exact sweep commands:

```sh
python3 scripts/collect_yosys_pr_candidates.py --out data/yosys_pr_candidates.json
modal run scripts/modal_yosys_gradient_sweep.py::main --max-prs-per-repo 2 --out data/yosys_verified_gradients_smoke.jsonl
modal run scripts/modal_yosys_gradient_sweep.py::main --no-require-tests --max-modules-per-pr 50 --out data/yosys_verified_gradients.jsonl
modal run scripts/modal_yosys_gradient_sweep.py::main --no-require-tests --max-modules-per-pr 0 --only 'chipsalliance/Cores-VeeR-EL2#296,chipsalliance/Cores-VeeR-EL2#247,chipsalliance/Cores-VeeR-EL2#182,vortexgpgpu/vortex#185,vortexgpgpu/vortex#176' --out data/yosys_verified_gradients_cap_hit.jsonl
```

Modal runs:

- Smoke: https://modal.com/apps/yc-hack27/main/ap-9ItJC66HR6FH79iKGKgC3l
- Full 50-module sweep: https://modal.com/apps/yc-hack27/main/ap-IIW36chI4ENg2x5InEgCqv
- Uncapped cap-hit follow-up: https://modal.com/apps/yc-hack27/main/ap-tpc5zzs6lSUrPevyrZOPjx

Data outputs:

- `data/yosys_pr_candidates.json`: collected PR/file metadata.
- `data/yosys_verified_gradients.jsonl`: final per-PR sweep results after merging the uncapped cap-hit follow-up.
- `data/yosys_verified_gradients_cap_hit.jsonl`: audit file for the five PRs that hit the 50-module cap.

## Result Summary

The final sweep covers 255 merged RTL/source PRs. It found 27 generated Yosys reward gradients. Of those, 24 are test-backed and 3 are source-only Yosys rewards.

| Repo | Swept PRs | Verified | Test-backed verified | Verdict shape |
| --- | ---: | ---: | ---: | --- |
| `Purdue-SoCET/atalla` | 137 | 9 | 8 | Mostly gold still fails under generated Yosys checks; several useful AI-accelerator/systolic-adjacent hits. |
| `YashKarthik/tpu` | 6 | 4 | 4 | Strongest TPU/systolic source. All four verified Yosys hits are test-backed. |
| `thousrm/universal_NPU-CNN_accelerator` | 20 | 7 | 5 | Strong NPU/MAC story; good next conversion target. |
| `kagandikmen/TPU.sv` | 3 | 1 | 1 | One generated synth reward; needs behavioral harness review before eval use. |
| `bradgrantham/alice5` | 1 | 0 | 0 | No generated Yosys gradient found in the swept PR. |
| `chipsalliance/Cores-VeeR-EL2` | 59 | 3 | 3 | Useful reference pattern, weaker RSI story because it is CPU-focused. |
| `vortexgpgpu/vortex` | 29 | 3 | 3 | GPU/control/tensor-adjacent generated rewards; lower priority than TPU/NPU hits. |

Final verdict totals:

| Verdict | Count |
| --- | ---: |
| `verified` | 27 |
| `gold_still_fails` | 205 |
| `unsuitable` | 18 |
| `base_already_passes` | 4 |
| `build_broken` | 1 |

## Verified Yosys Gradients

Full SHAs, complete file lists, logs, phase results, and per-candidate verdicts are in `data/yosys_verified_gradients.jsonl`.

| Repo | PR | Reward | Test-backed | Base | Gold | Module | RTL file | Title |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `Purdue-SoCET/atalla` | 176 | `yosys_equiv` | yes | `e8a086c9dc` | `7f099e1fe7` | `flex_counter` | `rtl/modules/ddr_cntrl/flex_counter.sv` | Ddr cntrl eddie |
| `Purdue-SoCET/atalla` | 175 | `yosys_synth` | yes | `61530cffd9` | `e8a086c9dc` | `flex_sr` | `rtl/modules/ddr_cntrl/flex_sr.sv` | Ddr cntrl jason |
| `Purdue-SoCET/atalla` | 173 | `yosys_synth` | yes | `ddaa842537` | `906662cdcf` | `flex_counter` | `rtl/modules/ddr_cntrl/flex_counter.sv` | Ddr cntrl jason |
| `Purdue-SoCET/atalla` | 128 | `yosys_synth` | yes | `8d6bd66b00` | `fce8f74f6a` | `axi_read_arbiter` | `src/modules/axi_read_arbiter.sv` | Memory subsystem aryan |
| `Purdue-SoCET/atalla` | 109 | `yosys_equiv` | yes | `c18b388d0a` | `785944acf3` | `ADD_step1` | `src/modules/ADD_step1.sv` | Systolic Array Final |
| `Purdue-SoCET/atalla` | 105 | `yosys_synth` | yes | `5f50177fab` | `a21cd35045` | `left_shift` | `src/NOTUSED/left_shift.sv` | Sp sa integration |
| `Purdue-SoCET/atalla` | 44 | `yosys_synth` | yes | `fd18bd9c55` | `d97caf9b3f` | `caches` | `src/modules/caches.sv` | Timmy sunday |
| `Purdue-SoCET/atalla` | 25 | `yosys_synth` | no | `9a8963977e` | `f35291a54c` | `FIFO` | `src/modules/sysarr_FIFO.sv` | Renamed modules to avoid conflicts |
| `Purdue-SoCET/atalla` | 2 | `yosys_equiv` | yes | `6570a9e91b` | `c496c8a4b7` | `flex_counter` | `src/modules/flex_counter.sv` | Generalize the makefile to apply to any module |
| `YashKarthik/tpu` | 8 | `yosys_equiv` | yes | `694c7bd404` | `b37948b2db` | `PE` | `src/PE.v` | Integrate Minimum Viable Product |
| `YashKarthik/tpu` | 6 | `yosys_equiv` | yes | `291f0b4f9d` | `9c579d5e4d` | `PE` | `src/PE.v` | Allowed repeated matmul |
| `YashKarthik/tpu` | 3 | `yosys_synth` | yes | `2cbb0637e4` | `c434ec5751` | `PE` | `src/PE.v` | Redo systolic array |
| `YashKarthik/tpu` | 1 | `yosys_synth` | yes | `68cd21010f` | `2eb1201971` | `controller` | `src/controller.v` | Incorporate Independent Matmul Unit |
| `thousrm/universal_NPU-CNN_accelerator` | 68 | `yosys_equiv` | yes | `90b13e2a39` | `78739777b4` | `mac_2s_complement` | `npu_v2/RTL/MAC/mac_2s_complement.sv` | debugging mac_lane int mode |
| `thousrm/universal_NPU-CNN_accelerator` | 67 | `yosys_equiv` | yes | `96aee011f4` | `90b13e2a39` | `mac_multiplier_mid` | `npu_v2/RTL/MAC/mac_multiplier_mid.sv` | desinging mac_lane |
| `thousrm/universal_NPU-CNN_accelerator` | 61 | `yosys_synth` | yes | `3e4bf3d5c4` | `83dfa85ea9` | `wallace_tree` | `npu_v2/RTL/MAC/wallace_tree.sv` | design wallace tree |
| `thousrm/universal_NPU-CNN_accelerator` | 57 | `yosys_synth` | no | `def984e7d8` | `890e5a2c7e` | `mac_2s_complement` | `npu_v2/RTL/MAC/mac_2s_complement.sv` | designing mac lane |
| `thousrm/universal_NPU-CNN_accelerator` | 56 | `yosys_equiv` | yes | `eddbc9bec5` | `def984e7d8` | `find_leading_one` | `npu_v2/RTL/common/find_leading_one.sv` | fix fp32 adder & design find_max |
| `thousrm/universal_NPU-CNN_accelerator` | 55 | `yosys_equiv` | no | `83cc50af67` | `eddbc9bec5` | `mac_multiplier_mid` | `npu_v2/RTL/MAC/mac_multiplier_mid.sv` | fix fp32 adder & designing mac lane |
| `thousrm/universal_NPU-CNN_accelerator` | 53 | `yosys_synth` | yes | `3ed43842ab` | `1fd6912048` | `mac_multiplier_big` | `npu_v2/RTL/MAC/mac_multiplier_big.sv` | preparing v2 |
| `kagandikmen/TPU.sv` | 3 | `yosys_synth` | yes | `8452fc98ad` | `de85814289` | `dist_ram` | `hdl/rtl/dist_ram.sv` | Implement SDK |
| `chipsalliance/Cores-VeeR-EL2` | 330 | `yosys_equiv` | yes | `338e7a0afe` | `98aac67b33` | `el2_ram` | `design/lib/mem_lib.sv` | Tlu ctl pmp |
| `chipsalliance/Cores-VeeR-EL2` | 259 | `yosys_equiv` | yes | `78cac32bfc` | `fe63594a77` | `dmi_mux` | `design/dmi/dmi_mux.v` | export DMI signals |
| `chipsalliance/Cores-VeeR-EL2` | 156 | `yosys_synth` | yes | `685da9e967` | `882fd9ff2c` | `dmi_mux` | `design/dmi/dmi_mux.v` | Add DMI mux with DMI tests |
| `vortexgpgpu/vortex` | 352 | `yosys_synth` | yes | `143d2cd4c5` | `15ec2f8779` | `VX_axi_arb2` | `hw/rtl/libs/VX_axi_arb2.sv` | Feature cp |
| `vortexgpgpu/vortex` | 345 | `yosys_synth` | yes | `edca3479ba` | `4304ee4e1d` | `VX_tex_lerp` | `hw/rtl/tex/VX_tex_lerp.sv` | gfx migration: full TLM-aligned simx + RTL CSR plumbing for draw3d |
| `vortexgpgpu/vortex` | 185 | `yosys_synth` | yes | `847562be9e` | `91c135ac15` | `VX_axi_write_ack` | `hw/rtl/libs/VX_axi_write_ack.sv` | Merge tensor-core and devel branch into master |

## Recommendation

Do not present all 27 as behavioral verified gradients. They are useful generated-reward gradients, and 24 have accompanying test/harness deltas, but the current proof is Yosys synthesis/equivalence, not simulator-observed functional pass/fail.

Best next conversions for the RL environment:

- `YashKarthik/tpu` PRs #6, #8, #3, and #1. These are compact TPU/systolic-array candidates and fit the RSI story best.
- `thousrm/universal_NPU-CNN_accelerator` PRs #68, #67, #61, #56, and #53. These give NPU/MAC/floating-point module rewards with a strong accelerator narrative.
- `Purdue-SoCET/atalla` PR #109 first, then #105 and #25 if manual RTL review confirms useful systolic-array or FPU task boundaries.

Use VeeR and Vortex as fallback/reference patterns. They are technically useful, but the hackathon story is stronger if the headline corpus centers TPU/NPU/systolic-array blocks.
