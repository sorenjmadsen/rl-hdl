"""PPA scorer: gate count via Yosys synthesis.

This runs ONLY on designs that already passed the equivalence gate, so we are
always ranking among circuits that are provably the same function. Gate count is
the primary PPA metric for v1; timing/area-from-liberty are secondary upgrades.

We run a generic `synth` (technology-independent), which does its own
optimization — that is deliberate: it makes the area number hard to game with
cosmetic rewrites (the synthesizer flattens those away). Real headroom is a
genuinely different structure that survives synthesis.

Yosys is not assumed to be on the local PATH. If it is missing, `synth_cells`
raises YosysUnavailable and the caller falls back to an equivalence-only verdict;
the full PPA path runs in the Modal container image (which ships Yosys).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_LOG_CAP = 4000
# Older Yosys `stat` prints e.g. "   Number of cells:                 42".
_NUMBERED_CELLS_RE = re.compile(r"Number of cells:\s+(\d+)")
# Newer Yosys versions print a compact table row, e.g. "     362 cells".
_TABLE_CELLS_RE = re.compile(r"(?m)^\s*(\d+)\s+cells\s*$")
# `stat -liberty` reports real area, e.g. "Chip area for module '\mul8': 1234.5".
# Some versions print "Chip area for top module ...". Capture either.
_CHIP_AREA_RE = re.compile(r"Chip area for(?: top)? module .*?:\s*([\d.]+)")


class YosysUnavailable(RuntimeError):
    """Raised when no yosys binary is on PATH."""


@dataclass(frozen=True)
class AreaResult:
    cells: int
    log: str


@dataclass(frozen=True)
class LibertyArea:
    """Real standard-cell area (um^2) from liberty-mapped synthesis."""

    area_um2: float
    log: str


def yosys_available() -> bool:
    return shutil.which("yosys") is not None


def liberty_path() -> str | None:
    """Path to a liberty (.lib) standard-cell library for real-area synthesis.

    Read from RLHDL_LIBERTY (the Modal image ships an open cell library and sets
    it). When unset or the file is missing, real-area (um^2) measurement is
    skipped and only the technology-independent cell-count metric is computed —
    so local dev and the current reward are completely unaffected.
    """
    p = os.environ.get("RLHDL_LIBERTY")
    return p if p and Path(p).is_file() else None


def _cell_count_from_stat(stdout: str) -> int | None:
    """Return the final top-module cell count from Yosys `stat` output."""
    matches = _NUMBERED_CELLS_RE.findall(stdout)
    if matches:
        return int(matches[-1])

    matches = _TABLE_CELLS_RE.findall(stdout)
    if matches:
        return int(matches[-1])

    return None


def _chip_area_from_stat(stdout: str) -> float | None:
    """Return the final top-module chip area from Yosys `stat -liberty` output."""
    matches = _CHIP_AREA_RE.findall(stdout)
    return float(matches[-1]) if matches else None


def synth_area_um2(rtl: str, top_module: str, *, liberty: str, timeout: float = 120.0) -> LibertyArea:
    """Map `rtl` to a real standard-cell library and return its area in um^2.

    Same generic `synth -flatten` front-end as synth_cells (so the structure
    being measured is identical), then technology mapping against `liberty`
    (dfflibmap for sequential cells + abc for combinational) and `stat -liberty`
    for the real area number. Raises YosysUnavailable if yosys is missing,
    RuntimeError on a tool or parse failure.
    """
    exe = shutil.which("yosys")
    if exe is None:
        raise YosysUnavailable("yosys not found on PATH; the PPA stage runs in the Modal image.")

    workdir = Path(tempfile.mkdtemp(prefix="rlhdl_libarea_"))
    try:
        src = workdir / "design.sv"
        src.write_text(rtl)
        script = (
            f"read_verilog -sv {src.name}; "
            f"synth -flatten -top {top_module}; "
            f"dfflibmap -liberty {liberty}; "
            f"abc -liberty {liberty}; "
            f"stat -liberty {liberty}"
        )
        proc = subprocess.run(
            [exe, "-p", script],
            cwd=workdir, capture_output=True, text=True, timeout=timeout,
        )
        log = (proc.stdout + "\n" + proc.stderr)[-_LOG_CAP:]
        if proc.returncode != 0:
            raise RuntimeError(f"yosys liberty synth failed (rc={proc.returncode}):\n{log}")
        area = _chip_area_from_stat(proc.stdout)
        if area is None:
            raise RuntimeError(f"could not parse chip area from yosys output:\n{log}")
        return LibertyArea(area, log)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def synth_cells(rtl: str, top_module: str, *, timeout: float = 120.0) -> AreaResult:
    """Synthesize `rtl` and return its post-synthesis cell count.

    Raises YosysUnavailable if yosys is not installed.
    """
    exe = shutil.which("yosys")
    if exe is None:
        raise YosysUnavailable("yosys not found on PATH; the PPA stage runs in the Modal image.")

    workdir = Path(tempfile.mkdtemp(prefix="rlhdl_ppa_"))
    try:
        src = workdir / "design.sv"
        src.write_text(rtl)
        # -flatten so cross-module structure can't hide cells; generic synth keeps
        # the metric technology-independent and reproducible without a liberty file.
        script = f"read_verilog -sv {src.name}; synth -flatten -top {top_module}; stat"
        proc = subprocess.run(
            [exe, "-p", script],
            cwd=workdir, capture_output=True, text=True, timeout=timeout,
        )
        log = (proc.stdout + "\n" + proc.stderr)[-_LOG_CAP:]
        if proc.returncode != 0:
            raise RuntimeError(f"yosys failed (rc={proc.returncode}):\n{log}")
        # The last cell-count row is the top module's flattened total.
        cells = _cell_count_from_stat(proc.stdout)
        if cells is None:
            raise RuntimeError(f"could not parse cell count from yosys output:\n{log}")
        return AreaResult(cells, log)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
