"""Equivalence gate: is a candidate rewrite still the same circuit as the golden?

This is stage 1+2 of the gate-then-climb grader. We compile the candidate and
the task's golden reference into ONE Verilator binary, drive identical random
vectors into both, and compare every output with `===`. A single mismatch on any
vector means "not equivalent" — no PPA credit downstream.

We reuse the combinational testbench generator from the v1 verifier (it already
instantiates candidate + `_ref` side by side); this module just turns its
pass/total into a structured equivalence verdict instead of a blended reward.

Verilator (randomized co-sim) is the v1 oracle. Formal equivalence via Yosys
`eqy`/SymbiYosys is the stretch upgrade and slots in behind the same interface.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cologic.extract import extract_module, module_name, rename_module
from cologic.schema import Task
from cologic.verifier import _RESULT_RE, build_testbench

_LOG_CAP = 4000


@dataclass(frozen=True)
class EquivResult:
    """Verdict of the equivalence gate.

    stage is one of:
      "no_module"      - nothing module-shaped in the candidate text
      "compile_error"  - candidate + ref + tb did not build
      "sim_error"      - built but the run produced no RESULT line
      "checked"        - ran to completion; `equivalent` is meaningful
    """

    stage: str
    compiled: bool
    equivalent: bool
    passed: int
    total: int
    candidate: str | None
    log: str


def check_equivalence(candidate_rtl: str, task: Task, *, timeout: float = 60.0) -> EquivResult:
    """Decide whether `candidate_rtl` is equivalent to `task.reference_rtl`.

    `candidate_rtl` may be raw model output (fenced/prose) or a bare module; we
    extract the module named `task.top_module` (falling back to the last module).
    """
    candidate = extract_module(candidate_rtl, task.top_module)
    if candidate is None:
        return EquivResult("no_module", False, False, 0, 0, None, "")

    # Force the candidate's top name to the required one so the tb can bind it.
    cand_name = module_name(candidate)
    if cand_name and cand_name != task.top_module:
        candidate = rename_module(candidate, cand_name, task.top_module)

    reference = rename_module(task.reference_rtl, task.top_module, f"{task.top_module}_ref")

    workdir = Path(tempfile.mkdtemp(prefix="rlhdl_eq_"))
    try:
        (workdir / "candidate.sv").write_text(candidate)
        (workdir / "reference.sv").write_text(reference)
        (workdir / "tb.sv").write_text(build_testbench(task))

        build = subprocess.run(
            [
                _verilator(), "--binary", "--timing", "-Wno-fatal",
                "--top-module", "tb", "-o", "sim",
                "--Mdir", str(workdir / "obj"),
                "-O0", "-CFLAGS", "-O0",
                "tb.sv", "candidate.sv", "reference.sv",
            ],
            cwd=workdir, capture_output=True, text=True, timeout=timeout,
        )
        if build.returncode != 0:
            return EquivResult("compile_error", False, False, 0, 0, candidate, build.stderr[-_LOG_CAP:])

        run = subprocess.run(
            [str(workdir / "obj" / "sim")], cwd=workdir, capture_output=True, text=True, timeout=timeout,
        )
        m = _RESULT_RE.search(run.stdout)
        if m is None:
            return EquivResult(
                "sim_error", True, False, 0, 0, candidate,
                (run.stdout + "\n" + run.stderr)[-_LOG_CAP:],
            )

        passed, total = int(m.group(1)), int(m.group(2))
        equivalent = total > 0 and passed == total
        return EquivResult("checked", True, equivalent, passed, total, candidate, run.stdout[-_LOG_CAP:])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _verilator() -> str:
    exe = shutil.which("verilator")
    if exe is None:
        raise RuntimeError("verilator not found on PATH; install it (brew install verilator).")
    return exe
