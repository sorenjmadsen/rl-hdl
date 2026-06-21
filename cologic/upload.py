"""Turn raw (uploaded) Verilog into a gradeable Task.

The end-user flow is "upload a Verilog module + ask to optimize it" — so we must
build a `Task` (the grader's input) from arbitrary RTL, not a hardcoded registry.
The one thing the grader needs that isn't in the RTL text is the **interface**
(port names/directions/widths) to wire its equivalence testbench; we parse it from
the module's ANSI header, with an optional explicit override for anything the
parser can't handle.

Best-effort, combinational-focused (v1). Handles ANSI headers like
`module m(input [7:0] a, input b, output [15:0] y);`, including comma-grouped
ports that inherit the prior direction/width (`input [7:0] a, b`). For exotic
headers, pass `interface=[Port(...), ...]` explicitly.
"""

from __future__ import annotations

import re

from cologic.extract import extract_module, module_name
from cologic.schema import Port, Task

_HEADER = re.compile(r"\bmodule\s+\w+\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;", re.DOTALL)
_DIR = re.compile(r"^\s*(input|output|inout)\b")
_WIDTH = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")
_CLOCK_LIKE = {"clk", "clock", "rst", "reset", "rst_n", "resetn", "rstn", "clk_i", "rst_i"}


def _split_top_level(body: str) -> list[str]:
    """Split a port list on commas that are not inside [] or ()."""
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def parse_interface(rtl: str, top_module: str | None = None) -> tuple[str, list[Port]]:
    """Parse (top_module, ports) from a module's ANSI header. Raises if unparseable."""
    mod = extract_module(rtl, top_module) or rtl
    top = top_module or module_name(mod)
    if not top:
        raise ValueError("could not find a module declaration")
    m = _HEADER.search(mod)
    if not m:
        raise ValueError(f"could not parse an ANSI port header for module {top!r}")

    ports: list[Port] = []
    last_dir: str | None = None
    last_width = 1
    for seg in _split_top_level(m.group(1)):
        if not seg.strip():
            continue
        dm = _DIR.match(seg)
        has_dir = dm is not None
        if has_dir:
            last_dir = dm.group(1)
            seg = seg[dm.end():]
        if last_dir is None:
            continue  # parameter/blank before any direction
        wm = _WIDTH.search(seg)
        if wm:
            last_width = abs(int(wm.group(1)) - int(wm.group(2))) + 1
            seg = seg[:wm.start()] + seg[wm.end():]
        elif has_dir:
            last_width = 1  # direction restated without a width => scalar, new group
        # else: bare continuation -> inherit last_dir and last_width
        seg = re.sub(r"\b(wire|reg|logic|signed)\b", " ", seg)
        name = seg.strip().split()[-1] if seg.strip() else None
        if name and name.isidentifier():
            ports.append(Port(name, last_dir, last_width))
    if not ports:
        raise ValueError(f"parsed no ports for module {top!r}")
    return top, ports


def is_clocked(ports: list[Port]) -> bool:
    return any(p.name.lower() in _CLOCK_LIKE for p in ports)


def task_from_rtl(
    rtl: str,
    *,
    task_id: str = "uploaded",
    top_module: str | None = None,
    interface: list[Port] | None = None,
    n_vectors: int = 256,
    seed: int = 1,
    spec: str = "Optimize this Verilog module for gate count while preserving its function.",
) -> Task:
    """Build a gradeable Task from raw RTL. Parses the interface unless given one."""
    if interface is not None:
        top = top_module or module_name(extract_module(rtl, top_module) or rtl)
        ports = interface
    else:
        top, ports = parse_interface(rtl, top_module)
    return Task(
        task_id=task_id,
        top_module=top,
        spec=spec,
        interface=ports,
        reference_rtl=rtl,
        n_vectors=n_vectors,
        seed=seed,
        clocked=is_clocked(ports),
        tags=["uploaded"],
    )
