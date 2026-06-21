"""Build and smoke-test the Modal OSS RTL verification toolchain.

Usage:
    modal run scripts/modal_rtl_toolchain.py

This image is intentionally OSS-only.  It covers the tools needed for the
verified-gradient sweep:

- Icarus Verilog + cocotb for YashKarthik/tpu.
- Verilator + C++ build tools for TPU.sv, universal_NPU, alice5, and fallback
  direct SystemVerilog probes.
- Yosys/GHDL for synthesis/formal-ish and VHDL fallback probes.
- Common build utilities used by open RTL repos.
"""

from __future__ import annotations

import json
import modal


app = modal.App("rl-hdl-rtl-toolchain")

RTL_TOOLCHAIN_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "autoconf",
        "automake",
        "binutils-riscv64-unknown-elf",
        "bison",
        "boolector",
        "build-essential",
        "ca-certificates",
        "ccache",
        "cmake",
        "curl",
        "device-tree-compiler",
        "file",
        "flex",
        "g++",
        "gcc",
        "gcc-riscv64-unknown-elf",
        "gdb",
        "ghdl",
        "git",
        "gperf",
        "iverilog",
        "jq",
        "libelf-dev",
        "libffi-dev",
        "libfl-dev",
        "libreadline-dev",
        "libssl-dev",
        "libtool",
        "make",
        "ninja-build",
        "patch",
        "perl",
        "pkg-config",
        "python3-dev",
        "python3-venv",
        "tcl-dev",
        "time",
        "unzip",
        "verilator",
        "wget",
        "yosys",
        "z3",
        "zlib1g-dev",
    )
    .pip_install(
        "cocotb==1.9.2",
        "cocotb-bus==0.2.1",
        "numpy==2.1.3",
        "pytest==8.3.4",
        "pyyaml==6.0.2",
        "tabulate==0.9.0",
        "tomli==2.0.2",
    )
    # Open standard-cell library for real-area (um^2) synthesis. The grader reads
    # RLHDL_LIBERTY; real area is observe-only (reward still ranks on cell count),
    # so a fetch failure cannot affect grading. Swap URL+path for Sky130 if wanted.
    .run_commands(
        "mkdir -p /opt/pdk && curl -fsSL "
        "https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/"
        "master/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib "
        "-o /opt/pdk/NangateOpenCellLibrary_typical.lib"
    )
    .env({"RLHDL_LIBERTY": "/opt/pdk/NangateOpenCellLibrary_typical.lib"})
)


@app.function(image=RTL_TOOLCHAIN_IMAGE, timeout=900)
def smoke_test_toolchain() -> dict:
    import os
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    env = os.environ.copy()
    env.pop("VERILATOR_ROOT", None)

    def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> dict:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }

    versions = {
        "git": run(["git", "--version"]),
        "make": run(["make", "--version"]),
        "gcc": run(["gcc", "--version"]),
        "g++": run(["g++", "--version"]),
        "python": run(["python", "--version"]),
        "iverilog": run(["iverilog", "-V"]),
        "vvp": run(["vvp", "-V"]),
        "verilator": run(["verilator", "--version"]),
        "yosys": run(["yosys", "-V"]),
        "ghdl": run(["ghdl", "--version"]),
        "pytest": run(["python", "-m", "pytest", "--version"]),
        "cocotb": run(["python", "-c", "import cocotb; print(cocotb.__version__)"]),
    }

    tmp = Path(tempfile.mkdtemp(prefix="rtl_toolchain_smoke_"))
    try:
        verilog = tmp / "and2.v"
        verilog.write_text(
            "module and2(input a, input b, output y); assign y = a & b; endmodule\n"
            "module tb; reg a=0,b=0; wire y; and2 dut(a,b,y); initial begin "
            "#1 a=1; b=1; #1 if (y !== 1'b1) $fatal; $finish; end endmodule\n"
        )
        synth_verilog = tmp / "and2_synth.v"
        synth_verilog.write_text("module and2(input a, input b, output y); assign y = a & b; endmodule\n")
        iverilog_build = run(["iverilog", "-g2012", "-s", "tb", "-o", "and2.vvp", "and2.v"], cwd=tmp)
        iverilog_run = run(["vvp", "and2.vvp"], cwd=tmp) if iverilog_build["returncode"] == 0 else None

        verilator_build = run(
            ["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "tb", "and2.v"],
            cwd=tmp,
            timeout=180,
        )
        verilator_run = run(["obj_dir/Vtb"], cwd=tmp) if verilator_build["returncode"] == 0 else None

        yosys_check = run(["yosys", "-p", "read_verilog and2_synth.v; prep -top and2"], cwd=tmp)

        vhdl = tmp / "and2_vhdl.vhd"
        vhdl.write_text(
            "library ieee; use ieee.std_logic_1164.all;\n"
            "entity and2_vhdl is port(a,b: in std_logic; y: out std_logic); end;\n"
            "architecture rtl of and2_vhdl is begin y <= a and b; end;\n"
        )
        ghdl_analyze = run(["ghdl", "-a", "and2_vhdl.vhd"], cwd=tmp)

        checks = {
            "iverilog_build": iverilog_build,
            "iverilog_run": iverilog_run,
            "verilator_build": verilator_build,
            "verilator_run": verilator_run,
            "yosys_check": yosys_check,
            "ghdl_analyze": ghdl_analyze,
            "riscv_gcc": run(["riscv64-unknown-elf-gcc", "--version"]),
            "z3": run(["z3", "--version"]),
            "boolector": run(["boolector", "--version"]),
        }

        ok = all(
            item is not None and item["returncode"] == 0
            for item in checks.values()
        )
        return {"ok": ok, "versions": versions, "checks": checks}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(smoke_test_toolchain.remote(), indent=2))
