"""Sweep Vortex GPGPU verified-gradient candidates on Modal.

Usage:
    modal run scripts/modal_vortex_gradients.py

Each candidate is reconstructed as:

1. base commit as-is
2. base commit plus only test/harness files from gold
3. gold commit

The counted verified-gradient condition is base+test FAIL and gold PASS.
"""

from __future__ import annotations

import json

import modal


app = modal.App("rl-hdl-vortex-gradients")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "autoconf",
        "automake",
        "binutils-riscv64-unknown-elf",
        "bison",
        "build-essential",
        "ca-certificates",
        "ccache",
        "cmake",
        "curl",
        "file",
        "flex",
        "g++",
        "gcc",
        "gdb",
        "git",
        "gperf",
        "iverilog",
        "jq",
        "libboost-serialization-dev",
        "libffi-dev",
        "libfl-dev",
        "libpng-dev",
        "libreadline-dev",
        "libssl-dev",
        "libtool",
        "make",
        "ninja-build",
        "ocl-icd-opencl-dev",
        "opencl-headers",
        "patch",
        "perl",
        "pkg-config",
        "python3-dev",
        "python3-venv",
        "time",
        "unzip",
        "uuid-dev",
        "verilator",
        "wget",
        "zlib1g-dev",
    )
)


CANDIDATES = [
    {
        "id": "vortex_cp_engine_unit_intro",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "f16da81b45e328cdb9fa1eba177bb68b31c5585f",
        "title": "hw/cp: VX_cp_engine FSM + bid interfaces + verilator unit test",
        "base_sha": "a1ab5d3749bcb0fde0451ecb4d0a544e28dc37d5",
        "gold_sha": "f16da81b45e328cdb9fa1eba177bb68b31c5585f",
        "unit": "cp_engine",
        "test_files": [
            "hw/unittest/Makefile",
            "hw/unittest/cp_engine/Makefile",
            "hw/unittest/cp_engine/VX_cp_engine_top.sv",
            "hw/unittest/cp_engine/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_engine.sv",
            "hw/rtl/cp/VX_cp_if.sv",
        ],
    },
    {
        "id": "vortex_cp_engine_done_gating",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "196c4e56111ec0742492a35c0b6097a1ebb9ca1b",
        "title": "hw/cp: engine retires on resource done, not on arbiter grant",
        "base_sha": "8b4fdc8b1677a1deb3f19f8bd043c1a4f5a48b44",
        "gold_sha": "196c4e56111ec0742492a35c0b6097a1ebb9ca1b",
        "unit": "cp_engine",
        "test_files": [
            "hw/unittest/cp_engine/VX_cp_engine_top.sv",
            "hw/unittest/cp_engine/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_core.sv",
            "hw/rtl/cp/VX_cp_engine.sv",
        ],
    },
    {
        "id": "vortex_cp_axil_regfile_legacy_strip",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "086d26b9f72e72b0cec95ba423da46eaf5dcb662",
        "title": "runtime: strip legacy launch_*/dcr_* from callbacks_t",
        "base_sha": "a43822c053acee193ddaeca8ef71f0efed321067",
        "gold_sha": "086d26b9f72e72b0cec95ba423da46eaf5dcb662",
        "unit": "cp_axil_regfile",
        "test_files": ["hw/unittest/cp_axil_regfile/VX_cp_axil_regfile_top.sv"],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_axil_regfile.sv",
            "hw/rtl/cp/VX_cp_core.sv",
        ],
    },
    {
        "id": "vortex_cp_dma_core_integration",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "d752346aedff84f6619dbff3a9dd81d59e187995",
        "title": "hw/cp: VX_cp_dma + full VX_cp_core integration + cp_core end-to-end TB",
        "base_sha": "535e060ffeb3fa2550ccfd9302f10bf46ed8d9a5",
        "gold_sha": "d752346aedff84f6619dbff3a9dd81d59e187995",
        "unit": "cp_core",
        "test_files": [
            "hw/unittest/Makefile",
            "hw/unittest/cp_core/Makefile",
            "hw/unittest/cp_core/VX_cp_core_top.sv",
            "hw/unittest/cp_core/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_core.sv",
            "hw/rtl/cp/VX_cp_dma.sv",
        ],
    },
    {
        "id": "vortex_cp_arbiter_unit_intro",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "a1ab5d3749bcb0fde0451ecb4d0a544e28dc37d5",
        "title": "hw/cp: VX_cp_arbiter + verilator unit test",
        "base_sha": "157e7a148121fe188536f39901f569d9c648f343",
        "gold_sha": "a1ab5d3749bcb0fde0451ecb4d0a544e28dc37d5",
        "unit": "cp_arbiter",
        "test_files": [
            "hw/unittest/Makefile",
            "hw/unittest/cp_arbiter/Makefile",
            "hw/unittest/cp_arbiter/VX_cp_arbiter_top.sv",
            "hw/unittest/cp_arbiter/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_arbiter.sv",
            "hw/rtl/cp/VX_cp_pkg.sv",
        ],
    },
    {
        "id": "vortex_cp_launch_unit_intro",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "6eb48a0e01f2e3e2fa292faa900d99b8967de9f3",
        "title": "hw/cp: VX_cp_launch FSM + verilator unit test",
        "base_sha": "f16da81b45e328cdb9fa1eba177bb68b31c5585f",
        "gold_sha": "6eb48a0e01f2e3e2fa292faa900d99b8967de9f3",
        "unit": "cp_launch",
        "test_files": [
            "hw/unittest/Makefile",
            "hw/unittest/cp_launch/Makefile",
            "hw/unittest/cp_launch/VX_cp_launch_top.sv",
            "hw/unittest/cp_launch/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/cp/VX_cp_launch.sv"],
    },
    {
        "id": "vortex_cp_dcr_proxy_unit_intro",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "7ee01f11b2ac16657e1dd7188a4c3d75c8ffbdc9",
        "title": "hw/cp: VX_cp_dcr_proxy FSM + verilator unit test",
        "base_sha": "6eb48a0e01f2e3e2fa292faa900d99b8967de9f3",
        "gold_sha": "7ee01f11b2ac16657e1dd7188a4c3d75c8ffbdc9",
        "unit": "cp_dcr_proxy",
        "test_files": [
            "hw/unittest/Makefile",
            "hw/unittest/cp_dcr_proxy/Makefile",
            "hw/unittest/cp_dcr_proxy/VX_cp_dcr_proxy_top.sv",
            "hw/unittest/cp_dcr_proxy/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/cp/VX_cp_dcr_proxy.sv"],
    },
    {
        "id": "vortex_cp_unpack_unit_intro",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "b7f0303defa42da9c0a097a9b9dccbc4729eb492",
        "title": "hw/cp: VX_cp_unpack + TB",
        "base_sha": "7ee01f11b2ac16657e1dd7188a4c3d75c8ffbdc9",
        "gold_sha": "b7f0303defa42da9c0a097a9b9dccbc4729eb492",
        "unit": "cp_unpack",
        "test_files": [
            "hw/unittest/Makefile",
            "hw/unittest/cp_unpack/Makefile",
            "hw/unittest/cp_unpack/VX_cp_unpack_top.sv",
            "hw/unittest/cp_unpack/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/cp/VX_cp_unpack.sv"],
    },
    {
        "id": "vortex_cache_elastic_bank_pipeline",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "pr": 371,
        "commit": "0bff36733b228aef8a99744db2ebbfc6a8cab299",
        "title": "cache: elastic bank pipeline with configurable latency + AMO timing fix",
        "base_sha": "1c6c3617ee9abc3b989323bdbec3583f1be9bf94",
        "gold_sha": "0bff36733b228aef8a99744db2ebbfc6a8cab299",
        "unit": "cache",
        "test_files": ["hw/unittest/cache/VX_cache_top.sv"],
        "gold_rtl_files": [
            "hw/rtl/cache/VX_cache.sv",
            "hw/rtl/cache/VX_cache_amo.sv",
            "hw/rtl/cache/VX_cache_bank.sv",
            "hw/rtl/cache/VX_cache_cluster.sv",
            "hw/rtl/cache/VX_cache_wrap.sv",
        ],
    },
    {
        "id": "vortex_cp_engine_event_unit",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "47edf04ee9bc001d5d2a9745b020b9729d400666",
        "title": "vortex2: timeline events + module/kernel handles + CP event unit",
        "base_sha": "a3b94b5154f4bc8b6b91c6061dc5ba1bd5ad4ef7",
        "gold_sha": "47edf04ee9bc001d5d2a9745b020b9729d400666",
        "unit": "cp_engine",
        "test_files": [
            "hw/unittest/cp_engine/VX_cp_engine_top.sv",
            "hw/unittest/cp_engine/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_core.sv",
            "hw/rtl/cp/VX_cp_engine.sv",
            "hw/rtl/cp/VX_cp_event_unit.sv",
            "hw/rtl/cp/VX_cp_pkg.sv",
        ],
    },
    {
        "id": "vortex_cp_v3_review_phase1",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "2d49de5d4ef6985c2f7c5ddf8878257ba679a551",
        "title": "cp v3 review Phase 1: runtime/RTL/AFU correctness fixes",
        "base_sha": "e9f33598bda367d140aba1d1bfd1448078e67335",
        "gold_sha": "2d49de5d4ef6985c2f7c5ddf8878257ba679a551",
        "unit": "cp_engine",
        "test_files": ["hw/unittest/cp_engine/VX_cp_engine_top.sv"],
        "gold_rtl_files": [
            "hw/rtl/afu/xrt/VX_afu_ctrl.sv",
            "hw/rtl/cp/VX_cp_completion.sv",
            "hw/rtl/cp/VX_cp_core.sv",
            "hw/rtl/cp/VX_cp_engine.sv",
        ],
    },
    {
        "id": "vortex_cp_xlen_lint_cleanup",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "4380ad5d726570084d71481d41f15825fba86258",
        "title": "ci: fix XLEN=32/64 regression bring-up + RTL lint-pragma cleanup",
        "base_sha": "0785ef461bcff65b55819c33ba8f9dc16b936d59",
        "gold_sha": "4380ad5d726570084d71481d41f15825fba86258",
        "unit": "cp_engine",
        "test_files": ["hw/unittest/cp_engine/VX_cp_engine_top.sv"],
        "gold_rtl_files": [
            "hw/rtl/cp/VX_cp_axil_regfile.sv",
            "hw/rtl/cp/VX_cp_core.sv",
            "hw/rtl/cp/VX_cp_dma.sv",
            "hw/rtl/cp/VX_cp_engine_bid_if.sv",
            "hw/rtl/cp/VX_cp_event_unit.sv",
            "hw/rtl/cp/VX_cp_gpu_if.sv",
            "hw/rtl/cp/VX_cp_if.sv",
        ],
    },
    {
        "id": "vortex_cp_v3_simx_finalize",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "eb9954b5728e625d293b256f72f7cac26da54234",
        "title": "cp: v3 SimX VM stack + finalize HW/SW integration",
        "base_sha": "fc3822b0b677a8cc3619cd66831d4614bed5bb96",
        "gold_sha": "eb9954b5728e625d293b256f72f7cac26da54234",
        "unit": "cp_engine",
        "test_files": [
            "hw/unittest/cp_engine/Makefile",
            "hw/unittest/cp_engine/VX_cp_engine_top.sv",
        ],
        "gold_rtl_files": [
            "hw/rtl/afu/xrt/vortex_afu.v",
            "hw/rtl/cp/VX_cp_axi_m_if.sv",
        ],
    },
    {
        "id": "vortex_tcu_drl_sparse_int_fmt8",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "6b722f3f8015740c41c22dc8906245c1112b4ba2",
        "title": "tcu_fedp: sparse integer alignment enable fix",
        "base_sha": "20d56ae3d7e3b87e7bc295fcdeb1bae9690f6d23",
        "gold_sha": "6b722f3f8015740c41c22dc8906245c1112b4ba2",
        "unit": "tcu_fedp",
        "tcu_backend": "drl",
        "opts": "--fmt=8 --tests=5000 --sparsity=50",
        "test_files": ["hw/unittest/tcu_fedp/main.cpp"],
        "gold_rtl_files": ["hw/rtl/tcu/drl/VX_tcu_fedp_drl.sv"],
    },
    {
        "id": "vortex_tcu_drl_sparse_int_fmt8_later",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "3655a931aea01fd604fef49946d95a8989b8e943",
        "title": "tcu_fedp: sparse integer alignment enable fix (later branch line)",
        "base_sha": "ca35a6d07608e11c6bd1f843f990577db902736c",
        "gold_sha": "3655a931aea01fd604fef49946d95a8989b8e943",
        "unit": "tcu_fedp",
        "tcu_backend": "drl",
        "opts": "--fmt=8 --tests=5000 --sparsity=50",
        "test_files": ["hw/unittest/tcu_fedp/main.cpp"],
        "gold_rtl_files": ["hw/rtl/tcu/drl/VX_tcu_fedp_drl.sv"],
    },
    {
        "id": "vortex_tcu_drl_accumulator_sign_extend",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "c8d171bc25fd304f8f2e0503f117e4d6537a3a6b",
        "title": "tcu_fedp: DRL accumulator sign extension bug",
        "base_sha": "7105968a2a9fd943b7b5970e042634d2b1efeaa7",
        "gold_sha": "c8d171bc25fd304f8f2e0503f117e4d6537a3a6b",
        "unit": "tcu_fedp",
        "tcu_backend": "drl",
        "opts": "--fmt=1 --tests=5000",
        "test_files": ["hw/unittest/tcu_fedp/fedp.h"],
        "gold_rtl_files": ["hw/rtl/tcu/drl/VX_tcu_drl_acc.sv"],
    },
    {
        "id": "vortex_tcu_drl_accumulator_sign_extend_later",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "38ac064e931e8af8304a2f0670fa1b6a0f2e7c14",
        "title": "tcu_fedp: DRL accumulator sign extension bug (later branch line)",
        "base_sha": "ec58fa65dc240ba45faf03ae614cb8c0a3c0348f",
        "gold_sha": "38ac064e931e8af8304a2f0670fa1b6a0f2e7c14",
        "unit": "tcu_fedp",
        "tcu_backend": "drl",
        "opts": "--fmt=1 --tests=5000",
        "test_files": ["hw/unittest/tcu_fedp/fedp.h"],
        "gold_rtl_files": ["hw/rtl/tcu/drl/VX_tcu_drl_acc.sv"],
    },
    {
        "id": "vortex_tcu_tfr_fp8_pipeline",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "b082cdb124723ee7e6176fbd6313d20662b8751e",
        "title": "tcu_fedp: TFR FP8 pipeline fix",
        "base_sha": "5f735f25b9091e5281c2330adbda6101601f9879",
        "gold_sha": "b082cdb124723ee7e6176fbd6313d20662b8751e",
        "unit": "tcu_fedp",
        "tcu_backend": "tfr",
        "opts": "--fmt=3 --tests=5000 --ulp=2 --features=infinities;nans;normals",
        "test_files": [
            "hw/unittest/tcu_fedp/Makefile",
            "hw/unittest/tcu_fedp/fedp.h",
        ],
        "gold_rtl_files": [
            "hw/rtl/tcu/tfr/VX_tcu_fedp_tfr.sv",
            "hw/rtl/tcu/tfr/VX_tcu_tfr_mul_f8.sv",
            "hw/rtl/tcu/tfr/VX_tcu_tfr_pipe_register.sv",
        ],
    },
    {
        "id": "vortex_tcu_tfr_fp8_pipeline_old_names",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "d3a50c331477f24c8757804ef948540fb09f748d",
        "title": "tcu_fedp: TFR FP8 pipeline fix (old module names)",
        "base_sha": "b1fa14b12fed619f16c342f90925265e02005716",
        "gold_sha": "d3a50c331477f24c8757804ef948540fb09f748d",
        "unit": "tcu_fedp",
        "tcu_backend": "tfr",
        "opts": "--fmt=3 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/Makefile",
            "hw/unittest/tcu_fedp/fedp.h",
        ],
        "gold_rtl_files": [
            "hw/rtl/tcu/tfr/VX_tcu_drl_mul_f8.sv",
            "hw/rtl/tcu/tfr/VX_tcu_fedp_tfr.sv",
            "hw/rtl/tcu/tfr/VX_tcu_tfr_pipe_register.sv",
        ],
    },
    {
        "id": "vortex_tcu_tfr_fp8_bf8_vectors",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "f22f69b8366bb5b78a3a1d13546fd21246c8565e",
        "title": "tcu_fedp: FP8/BF8 unit-test and multiplier fix",
        "base_sha": "b082cdb124723ee7e6176fbd6313d20662b8751e",
        "gold_sha": "f22f69b8366bb5b78a3a1d13546fd21246c8565e",
        "unit": "tcu_fedp",
        "tcu_backend": "tfr",
        "opts": "--fmt=4 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/fedp.py",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/tcu/tfr/VX_tcu_tfr_mul_f8.sv"],
    },
    {
        "id": "vortex_tcu_tfr_fp8_bf8_vectors_old_names",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "b390966b76b63483c505ae461e8b5a23e8a8745a",
        "title": "tcu_fedp: FP8/BF8 unit-test and multiplier fix (old module names)",
        "base_sha": "d3a50c331477f24c8757804ef948540fb09f748d",
        "gold_sha": "b390966b76b63483c505ae461e8b5a23e8a8745a",
        "unit": "tcu_fedp",
        "tcu_backend": "tfr",
        "opts": "--fmt=4 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/fedp.py",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/tcu/tfr/VX_tcu_drl_mul_f8.sv"],
    },
    {
        "id": "vortex_tcu_tfr_fp16_build_fix",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "9e350e2e83962cfda0d7a3ea935668a43fd7479c",
        "title": "tcu_fedp: TFR FP16 build/test fix",
        "base_sha": "486b85dbb84dae8b1ed6a378c3f0ab599e7e9598",
        "gold_sha": "9e350e2e83962cfda0d7a3ea935668a43fd7479c",
        "unit": "tcu_fedp",
        "tcu_backend": "tfr",
        "opts": "--fmt=1 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/tcu/tfr/VX_tcu_tfr_mul_f16.sv"],
    },
    {
        "id": "vortex_tcu_tfr_fp16_build_fix_old_names",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "591c05023db6a919709f8b6639cf032aba80f909",
        "title": "tcu_fedp: TFR FP16 build/test fix (old module names)",
        "base_sha": "70ff1638577825c148d11293ad47b260d511f1df",
        "gold_sha": "591c05023db6a919709f8b6639cf032aba80f909",
        "unit": "tcu_fedp",
        "tcu_backend": "tfr",
        "opts": "--fmt=1 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/tcu/tfr/VX_tcu_drl_mul_f16.sv"],
    },
    {
        "id": "vortex_tcu_drl_emulation_macros",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "8c19f62a60cbe6c9cc3d264154759f5bcf4c0e7b",
        "title": "tcu_fedp: DRL emulation macro fix",
        "base_sha": "ebb12a6b6c2130c123f2ef1f521fa15ef024ddb0",
        "gold_sha": "8c19f62a60cbe6c9cc3d264154759f5bcf4c0e7b",
        "unit": "tcu_fedp",
        "tcu_backend": "drl",
        "opts": "--fmt=1 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/tcu/drl/VX_tcu_fedp_drl.sv"],
    },
    {
        "id": "vortex_tcu_drl_emulation_macros_old_line",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "2b303f5e7d3fff1fdacc60ac352644096dd4763a",
        "title": "tcu_fedp: DRL emulation macro fix (old branch line)",
        "base_sha": "412122c92ad26a44c6471903cae482e85af5fa67",
        "gold_sha": "2b303f5e7d3fff1fdacc60ac352644096dd4763a",
        "unit": "tcu_fedp",
        "tcu_backend": "drl",
        "opts": "--fmt=1 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": ["hw/rtl/tcu/drl/VX_tcu_fedp_drl.sv"],
    },
    {
        "id": "vortex_tcu_bhf_fp8_unit",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "d73d3c629d0856fc698954fdcf9e73986ed1a34e",
        "title": "tcu_fedp: BHF/DPI FP8 unittest fix",
        "base_sha": "323e27f046f1d94d21e8ad0ec46639d33b10d550",
        "gold_sha": "d73d3c629d0856fc698954fdcf9e73986ed1a34e",
        "unit": "tcu_fedp",
        "tcu_backend": "bhf",
        "make_vars": ["LATENCY=13"],
        "opts": "--fmt=3 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/tcu/bhf/VX_tcu_bhf_fp8mul.sv",
            "hw/rtl/tcu/dpi/VX_tcu_fedp_dpi.sv",
        ],
    },
    {
        "id": "vortex_tcu_bhf_fp8_unit_old_line",
        "repo_url": "https://github.com/vortexgpgpu/vortex",
        "commit": "3d7c0ae49462aac23bf65aed71748872e9b4f369",
        "title": "tcu_fedp: BHF/DPI FP8 unittest fix (old branch line)",
        "base_sha": "c58be0a7059c23482b4e3de0915bdfbe2ac0b064",
        "gold_sha": "3d7c0ae49462aac23bf65aed71748872e9b4f369",
        "unit": "tcu_fedp",
        "tcu_backend": "bhf",
        "make_vars": ["LATENCY=13"],
        "opts": "--fmt=3 --tests=5000",
        "test_files": [
            "hw/unittest/tcu_fedp/fedp.h",
            "hw/unittest/tcu_fedp/main.cpp",
        ],
        "gold_rtl_files": [
            "hw/rtl/tcu/bhf/VX_tcu_bhf_fp8mul.sv",
            "hw/rtl/tcu/dpi/VX_tcu_fedp_dpi.sv",
        ],
    },
]


@app.function(image=image, timeout=7200, cpu=4)
def sweep_vortex_candidates(candidates: list[dict]) -> list[dict]:
    import os
    import re
    import shutil
    import subprocess
    from pathlib import Path

    root = Path("/tmp/rlhdl_vortex_modal")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    tools = Path("/opt/vortex-tools/verilator/bin")
    tools.mkdir(parents=True, exist_ok=True)
    verilator_wrapper = tools / "verilator"
    verilator_wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = [arg for arg in sys.argv[1:] if arg != '-Wno-GENUNNAMED']\n"
        "os.execv('/usr/bin/verilator', ['/usr/bin/verilator', '-Wno-fatal', *args])\n"
    )
    verilator_wrapper.chmod(0o755)

    repo = root / "vortex"
    subprocess.run(
        ["git", "clone", "https://github.com/vortexgpgpu/vortex", str(repo)],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )

    env = os.environ.copy()
    env.pop("VERILATOR_ROOT", None)
    env["THREADS"] = "2"

    def run(cmd: list[str], cwd: Path, *, timeout: int = 300) -> dict:
        try:
            proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
            return {
                "cmd": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-1600:],
                "stderr": proc.stderr[-1600:],
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "cmd": cmd,
                "returncode": 124,
                "stdout": (exc.stdout or "")[-1600:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-1600:] if isinstance(exc.stderr, str) else "timeout",
            }

    def configure(path: Path) -> dict:
        conf = run(["./configure", "--tooldir=/opt/vortex-tools", "--osversion=ubuntu/focal"], path, timeout=240)
        if conf["returncode"] == 0:
            strip_unsupported_verilator_pragmas(path)
        return conf

    def prepare_unit_deps(path: Path, unit: str) -> dict:
        if unit != "tcu_fedp":
            return {"returncode": 0, "stdout": "", "stderr": ""}

        config = run(["make", "-C", "hw", "config"], path, timeout=240)
        if config["returncode"] != 0:
            return config

        submodules = run(
            ["git", "submodule", "update", "--init", "third_party/softfloat", "third_party/hardfloat"],
            path,
            timeout=900,
        )
        if submodules["returncode"] != 0:
            return submodules

        softfloat = run(["make", "-C", "third_party", "softfloat", "-j2"], path, timeout=900)
        if softfloat["returncode"] != 0:
            return softfloat

        return {
            "returncode": 0,
            "stdout": config["stdout"] + submodules["stdout"] + softfloat["stdout"],
            "stderr": config["stderr"] + submodules["stderr"] + softfloat["stderr"],
        }

    def tcu_config_arg(path: Path, backend: str | None) -> str | None:
        if not backend:
            return None
        makefile = path / "hw" / "unittest" / "tcu_fedp" / "Makefile"
        text = makefile.read_text(errors="ignore") if makefile.exists() else ""
        if backend == "drl":
            if "TCU_TYPE_DRL" in text:
                return "CONFIGS=-DTCU_TYPE_DRL -DXLEN=32"
            return "CONFIGS=-DTCU_DRL -DXLEN=32"
        if backend == "tfr":
            return "CONFIGS=-DTCU_TYPE_TFR -DXLEN=32"
        if backend == "bhf":
            if "TCU_TYPE_BHF" in text:
                return "CONFIGS=-DTCU_TYPE_BHF -DXLEN=32"
            return "CONFIGS=-DTCU_BHF -DXLEN=32"
        return None

    def strip_unsupported_verilator_pragmas(path: Path) -> None:
        for root_name in ("hw/rtl", "hw/unittest"):
            root_path = path / root_name
            if not root_path.exists():
                continue
            for source in root_path.rglob("*"):
                if source.suffix not in {".v", ".vh", ".sv", ".svh", ".mk"} and source.name != "Makefile":
                    continue
                text = source.read_text(errors="ignore")
                patched = text.replace("GENUNNAMED", "UNOPTFLAT")
                if patched != text:
                    source.write_text(patched)

    def compact_phase(phase: dict) -> dict:
        out = {
            "passed": phase.get("passed", False),
            "stage": phase.get("stage"),
        }
        for key in ("configure", "prepare", "clean", "build", "test"):
            if key in phase and phase[key] is not None:
                item = phase[key]
                out[f"{key}_returncode"] = item.get("returncode")
                if item.get("returncode") not in (0, None):
                    out["failure_snippet"] = ((item.get("stdout") or "") + (item.get("stderr") or ""))[-1200:]
                    break
        return out

    def run_unit(path: Path, candidate: dict) -> dict:
        unit = candidate["unit"]
        conf = configure(path)
        unit_dir = path / "hw" / "unittest" / unit
        if conf["returncode"] != 0:
            return {"passed": False, "stage": "configure", "configure": conf}
        if not unit_dir.exists():
            return {"passed": False, "stage": "missing_unit_dir", "configure": conf}

        prepare = prepare_unit_deps(path, unit)
        if prepare["returncode"] != 0:
            return {"passed": False, "stage": "prepare", "configure": conf, "prepare": prepare}

        config_arg = tcu_config_arg(path, candidate.get("tcu_backend"))
        make_vars = [config_arg] if config_arg else []
        make_vars.extend(candidate.get("make_vars", []))
        opts = candidate.get("opts")
        run_vars = [*make_vars, f"OPTS={opts}"] if opts else make_vars

        clean = run(["make", "clean"], unit_dir, timeout=120)
        build = run(["make", *make_vars, "-j2"], unit_dir, timeout=1200)
        test = run(["timeout", "120s", "make", *run_vars, "run"], unit_dir, timeout=180) if build["returncode"] == 0 else None
        passed = clean["returncode"] == 0 and build["returncode"] == 0 and test is not None and test["returncode"] == 0
        return {
            "passed": passed,
            "stage": "run" if test is not None else "build",
            "configure": conf,
            "prepare": prepare,
            "clean": clean,
            "build": build,
            "test": test,
        }

    def gradient_kind(phase_a: dict, phase_b: dict) -> str:
        if not phase_b.get("passed"):
            return "none"
        if phase_a.get("stage") == "run" and (phase_a.get("build") or {}).get("returncode") == 0:
            return "behavioral_runtime"
        if phase_a.get("stage") == "build":
            return "compile_or_interface"
        return phase_a.get("stage") or "unknown"

    results = []
    for index, candidate in enumerate(candidates, start=1):
        cid = candidate["id"]
        print(f"[{index}/{len(candidates)}] {cid}", flush=True)
        base = root / f"{cid}_base"
        testonly = root / f"{cid}_testonly"
        gold = root / f"{cid}_gold"

        for path, sha in ((base, candidate["base_sha"]), (testonly, candidate["base_sha"]), (gold, candidate["gold_sha"])):
            proc = subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "--detach", str(path), sha],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                results.append({
                    **candidate,
                    "verdict": "build_broken",
                    "phase_a_result": "worktree add failed",
                    "phase_b_result": "not run",
                    "log": (proc.stdout + proc.stderr)[-1600:],
                })
                break
        else:
            patch = subprocess.run(
                ["git", "-C", str(repo), "diff", candidate["base_sha"], candidate["gold_sha"], "--", *candidate["test_files"]],
                capture_output=True,
                text=True,
                timeout=300,
            )
            apply = subprocess.run(
                ["git", "-C", str(testonly), "apply"],
                input=patch.stdout,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if patch.returncode != 0 or apply.returncode != 0:
                results.append({
                    **candidate,
                    "verdict": "build_broken",
                    "phase_a_result": "test patch did not apply",
                    "phase_b_result": "not run",
                    "log": (patch.stdout + patch.stderr + apply.stdout + apply.stderr)[-1600:],
                })
                continue

            base_original = run_unit(base, candidate)
            phase_a = run_unit(testonly, candidate)
            phase_b = run_unit(gold, candidate)

            intro_build_break = base_original.get("stage") == "missing_unit_dir" or "Can't find definition of module" in (
                (phase_a.get("build") or {}).get("stderr") or ""
            )

            if intro_build_break and phase_b["passed"]:
                verdict = "build_broken"
            elif not phase_a["passed"] and phase_b["passed"]:
                verdict = "verified"
            elif phase_a["passed"] and phase_b["passed"]:
                verdict = "base_already_passes"
            elif not phase_b["passed"]:
                verdict = "gold_still_fails"
            else:
                verdict = "unsuitable"

            result = {
                **candidate,
                "command": (
                    f"./configure --tooldir=/opt/vortex-tools --osversion=ubuntu/focal && "
                    f"make -C hw/unittest/{candidate['unit']} clean && "
                    f"make -C hw/unittest/{candidate['unit']} "
                    f"{' '.join([tcu_config_arg(gold, candidate.get('tcu_backend')) or '', *candidate.get('make_vars', [])]).strip()} -j2 && "
                    f"timeout 120s make -C hw/unittest/{candidate['unit']} "
                    f"{' '.join([tcu_config_arg(gold, candidate.get('tcu_backend')) or '', *candidate.get('make_vars', [])]).strip()} "
                    f"{('OPTS=' + candidate['opts']) if candidate.get('opts') else ''} run"
                ),
                "base_original": compact_phase(base_original),
                "clean_base": base_original["passed"],
                "phase_a": compact_phase(phase_a),
                "phase_b": compact_phase(phase_b),
                "gradient_kind": gradient_kind(phase_a, phase_b),
                "verdict": verdict,
            }
            print(f"[{index}/{len(candidates)}] {cid}: {verdict} {result['gradient_kind']}", flush=True)
            results.append(result)

    return results


@app.local_entrypoint()
def main(ids: str = "", start: int = 0, limit: int = 0) -> None:
    candidates = CANDIDATES
    if ids:
        wanted = {item.strip() for item in ids.split(",") if item.strip()}
        candidates = [candidate for candidate in candidates if candidate["id"] in wanted]
    if start or limit:
        end = None if limit == 0 else start + limit
        candidates = candidates[start:end]
    print(json.dumps(sweep_vortex_candidates.remote(candidates), indent=2))
