"""The grader: real silicon tooling (Verilator) as a non-lying oracle.

grade(completion, task) extracts the candidate module, builds a SystemVerilog
testbench that instantiates BOTH the candidate and the task's golden reference,
drives the same random input vectors into both, and counts how many output
comparisons match. Reward is correctness-dominant and dense:

    no extractable module   -> 0.00
    extracted, won't compile -> 0.05
    compiles but sim errors -> 0.05
    compiles + runs         -> 0.10 + 0.90 * (passed / total)

The 0.10 floor is the "partial credit for compiling" the RL de-risking calls for;
the rest is the fraction of (output x vector) comparisons that match the oracle.
"""

from __future__ import annotations

import os
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from cologic.extract import extract_module, extract_modules, module_name, rename_module
from cologic.schema import GradeResult, Task

COMPILE_FLOOR = 0.10
COMPILE_ERROR_REWARD = 0.05
_LOG_CAP = 4000
_RESULT_RE = re.compile(r"RESULT\s+(\d+)\s+(\d+)")


def _verilator() -> str:
    exe = shutil.which("verilator")
    if exe is None:
        raise RuntimeError("verilator not found on PATH; install it (brew install verilator).")
    return exe


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    # A stale VERILATOR_ROOT makes Homebrew Verilator fail before parsing files.
    env.pop("VERILATOR_ROOT", None)
    return env


def _extract_candidate(completion: str, task: Task) -> str | None:
    if not task.allow_extra_modules:
        return extract_module(completion, task.top_module)

    modules = extract_modules(completion)
    if not modules:
        return None

    selected = None
    for i, mod in enumerate(modules):
        if module_name(mod) == task.top_module:
            selected = i
            break
    if selected is None:
        selected = len(modules) - 1
        name = module_name(modules[selected])
        if name and name != task.top_module:
            modules[selected] = rename_module(modules[selected], name, task.top_module)

    return "\n\n".join(modules)


def _rand_rhs(width: int) -> str:
    """SystemVerilog RHS producing a random value at least `width` bits wide.

    Assignment to a narrower reg truncates to the low bits, which is fine.
    """
    n_chunks = max(1, math.ceil(width / 32))
    if n_chunks == 1:
        return "$urandom"
    return "{" + ", ".join(["$urandom"] * n_chunks) + "}"


def build_testbench(task: Task) -> str:
    """Generate a self-checking combinational testbench for `task`.

    Drives random vectors, compares every output of candidate vs reference with
    `===` (so an X on the candidate counts as a mismatch), and prints
    `RESULT <passed> <total>`.
    """
    if task.testbench_template:
        return (
            task.testbench_template
            .replace("__TASK_ID__", task.task_id)
            .replace("__DUT__", task.top_module)
            .replace("__REF__", f"{task.top_module}_ref")
            .replace("__N_VECTORS__", str(task.n_vectors))
            .replace("__SEED__", str(task.seed))
        )

    if task.clocked:
        raise NotImplementedError("clocked tasks require testbench_template.")

    decls: list[str] = []
    for p in task.inputs:
        w = "" if p.width == 1 else f"[{p.width - 1}:0] "
        decls.append(f"  logic {w}{p.name};")
    for p in task.outputs:
        w = "" if p.width == 1 else f"[{p.width - 1}:0] "
        decls.append(f"  logic {w}{p.name}__c;")
        decls.append(f"  logic {w}{p.name}__r;")

    def conn(suffix: str) -> str:
        parts = [f".{p.name}({p.name})" for p in task.inputs]
        parts += [f".{p.name}({p.name}{suffix})" for p in task.outputs]
        return ", ".join(parts)

    drive = "\n".join(f"      {p.name} = {_rand_rhs(p.width)};" for p in task.inputs)
    compare = "\n".join(
        f"      rlhdl_total += 1; if ({p.name}__c === {p.name}__r) rlhdl_pass += 1;"
        for p in task.outputs
    )

    # Internal tb names are rlhdl_-prefixed so they can't collide with a DUT port
    # named `i`, `total`, `passed`, etc. (real benchmark designs do this).
    return f"""// auto-generated testbench for task {task.task_id}
module tb;
{chr(10).join(decls)}

  {task.top_module}     dut_c ({conn("__c")});
  {task.top_module}_ref dut_r ({conn("__r")});

  integer rlhdl_i;
  integer rlhdl_pass = 0;
  integer rlhdl_total = 0;
  initial begin
    void'($urandom({task.seed}));
    for (rlhdl_i = 0; rlhdl_i < {task.n_vectors}; rlhdl_i = rlhdl_i + 1) begin
{drive}
      #1;
{compare}
      #1;
    end
    $display("RESULT %0d %0d", rlhdl_pass, rlhdl_total);
    $finish;
  end
endmodule
"""


def grade(completion: str, task: Task, *, keep_dir: bool = False, timeout: float = 60.0) -> GradeResult:
    """Grade an LLM completion against a task. The locked reward seam."""
    candidate = _extract_candidate(completion, task)
    if candidate is None:
        return GradeResult(0.0, {"stage": "no_module", "compiled": False, "passed": 0, "total": 0, "log": ""})

    # Force the candidate's top to the required name so the testbench can bind it.
    cand_name = module_name(extract_module(candidate, task.top_module) or candidate)
    if cand_name and cand_name != task.top_module and not task.allow_extra_modules:
        candidate = rename_module(candidate, cand_name, task.top_module)

    reference = rename_module(task.reference_rtl, task.top_module, f"{task.top_module}_ref")

    workdir = Path(tempfile.mkdtemp(prefix="rlhdl_"))
    try:
        (workdir / "candidate.sv").write_text(candidate)
        (workdir / "reference.sv").write_text(reference)
        (workdir / "tb.sv").write_text(build_testbench(task))

        build = subprocess.run(
            [
                _verilator(), "--binary", "--timing", "-Wno-fatal",
                "--top-module", "tb", "-o", "sim",
                "--Mdir", str(workdir / "obj"),
                # Grading is compile-bound, not sim-bound (tiny vector counts), so
                # skip host-compiler and Verilator optimization to speed turnaround.
                "-O0", "-CFLAGS", "-O0",
                "tb.sv", "candidate.sv", "reference.sv",
            ],
            cwd=workdir, capture_output=True, text=True, timeout=timeout, env=_subprocess_env(),
        )
        if build.returncode != 0:
            return GradeResult(
                COMPILE_ERROR_REWARD,
                {"stage": "compile_error", "compiled": False, "passed": 0, "total": 0,
                 "log": build.stderr[-_LOG_CAP:]},
            )

        run = subprocess.run(
            [str(workdir / "obj" / "sim")], cwd=workdir, capture_output=True, text=True, timeout=timeout,
            env=_subprocess_env(),
        )
        m = _RESULT_RE.search(run.stdout)
        if m is None:
            return GradeResult(
                COMPILE_ERROR_REWARD,
                {"stage": "sim_error", "compiled": True, "passed": 0, "total": 0,
                 "log": (run.stdout + "\n" + run.stderr)[-_LOG_CAP:]},
            )

        passed, total = int(m.group(1)), int(m.group(2))
        frac = passed / total if total else 0.0
        reward = COMPILE_FLOOR + (1.0 - COMPILE_FLOOR) * frac
        return GradeResult(
            round(reward, 6),
            {"stage": "graded", "compiled": True, "passed": passed, "total": total,
             "log": run.stdout[-_LOG_CAP:]},
        )
    finally:
        if not keep_dir:
            shutil.rmtree(workdir, ignore_errors=True)
