"""VerilogEval (NVlabs, MIT) -> cologic Tasks.

VerilogEval spec-to-RTL stores each problem as three files:
  Prob###_<name>_prompt.txt   complete NL spec (asks for a module `TopModule`)
  Prob###_<name>_ref.sv       reference solution, module `RefModule`
  Prob###_<name>_test.sv      a clock-driven stats testbench (their oracle)

For v1 we ingest the **combinational** subset and grade via our golden random
co-sim (Path B): rename the reference `RefModule` -> `TopModule` so the existing
grader's `TopModule` -> `TopModule_ref` rename binds it. The dataset testbench is
kept in the record for the future testbench-oracle path, but unused here.

`build_verilogeval_subset.py` converts a local clone into the committed JSON that
`load()` reads, so runtime/tests need no network and no redistribution of the raw
benchmark (only a curated, attributed subset; see NOTICE_verilogeval.md).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from cologic.schema import Port, Task

REF_NAME = "RefModule"
TOP_NAME = "TopModule"
_SUBSET_JSON = Path(__file__).with_name("verilogeval_combinational.json")

_HEADER_RE = re.compile(rf"module\s+{REF_NAME}\s*\((.*?)\)\s*;", re.DOTALL)
_PORT_RE = re.compile(r"^(input|output|inout)\b(.*)$", re.DOTALL)
_WIDTH_RE = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")
_NAME_RE = re.compile(r"(\w+)\s*$")
# Markers that make a design sequential / out of scope for combinational co-sim.
_SEQ_RE = re.compile(r"\b(clk|clock)\b|posedge|negedge|always_ff|always_latch")


def is_combinational(ref_sv: str) -> bool:
    return _SEQ_RE.search(ref_sv) is None


def parse_ports(ref_sv: str) -> list[Port] | None:
    """Parse RefModule's ANSI ports. None if any port is inout or unparseable
    (non-numeric width, missing direction) — we skip those problems."""
    m = _HEADER_RE.search(ref_sv)
    if not m:
        return None
    ports: list[Port] = []
    for frag in m.group(1).split(","):
        frag = frag.strip()
        if not frag:
            continue
        pm = _PORT_RE.match(frag)
        if not pm:
            return None
        direction, rest = pm.group(1), pm.group(2)
        if direction == "inout":
            return None
        width = 1
        if "[" in rest:
            wm = _WIDTH_RE.search(rest)
            if not wm:
                return None  # parametric / non-numeric width: skip
            hi, lo = int(wm.group(1)), int(wm.group(2))
            width = abs(hi - lo) + 1
            rest = rest[: wm.start()] + rest[wm.end() :]
        nm = _NAME_RE.search(rest.strip())
        if not nm:
            return None
        ports.append(Port(nm.group(1), direction, width))
    return ports or None


def convert_dir(spec_to_rtl_dir: str | Path) -> list[dict]:
    """Convert a local `dataset_spec-to-rtl` directory into task records."""
    d = Path(spec_to_rtl_dir)
    records: list[dict] = []
    for ref_path in sorted(d.glob("*_ref.sv")):
        stem = ref_path.name[: -len("_ref.sv")]
        ref = ref_path.read_text()
        if not is_combinational(ref):
            continue
        ports = parse_ports(ref)
        if not ports:
            continue
        prompt = (d / f"{stem}_prompt.txt").read_text().strip()
        test = (d / f"{stem}_test.sv").read_text()
        records.append({
            "task_id": stem,
            "spec": prompt,
            "top_module": TOP_NAME,
            "interface": [{"name": p.name, "direction": p.direction, "width": p.width} for p in ports],
            # rename so the grader's TopModule->TopModule_ref rename binds it
            "reference_rtl": ref.replace(f"module {REF_NAME}", f"module {TOP_NAME}", 1),
            "testbench": test,  # for the future testbench-oracle path; unused by golden co-sim
            "tags": ["verilogeval", "comb"],
        })
    return records


def _record_to_task(r: dict) -> Task:
    return Task(
        task_id=r["task_id"],
        spec=r["spec"],
        top_module=r["top_module"],
        interface=[Port(**p) for p in r["interface"]],
        reference_rtl=r["reference_rtl"],
        prompt_is_complete=True,
        tags=r.get("tags", []),
    )


def load() -> list[Task]:
    """Load the committed combinational subset as Tasks (golden co-sim)."""
    records = json.loads(_SUBSET_JSON.read_text())
    return [_record_to_task(r) for r in records]
