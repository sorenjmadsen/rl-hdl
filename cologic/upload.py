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
import textwrap

from cologic.extract import extract_module, extract_modules, module_name
from cologic.schema import Port, Task

_HEADER = re.compile(r"\bmodule\s+\w+\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;", re.DOTALL)
_DIR = re.compile(r"^\s*(input|output|inout)\b")
_WIDTH = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")
_CLOCK_LIKE = {"clk", "clock", "rst", "reset", "rst_n", "resetn", "rstn", "clk_i", "rst_i"}
# The clock the scaffold testbench free-runs. Resets/enables are left for the
# user's stimulus to drive; only the actual clock gets the `always` toggle.
_CLOCK_NAMES = {"clk", "clock", "clk_i", "clock_i"}


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


# ── multi-file ingestion (the upload flow) ─────────────────────────────────────


def concat_files(files: dict[str, str]) -> str:
    """Concatenate uploaded Verilog sources into one reference blob.

    Order is by filename for determinism; Verilator resolves cross-module
    references regardless of declaration order.
    """
    return "\n\n".join(files[name] for name in sorted(files))


def resolve_top(rtl: str, top_module: str | None = None) -> str:
    """Pick the top module among (possibly many) modules in `rtl`.

    If `top_module` is given, validate it exists. Otherwise the top is the module
    that no *other* module instantiates; raises if that is ambiguous so the caller
    (UI) can ask the user to choose.
    """
    modules = extract_modules(rtl)
    names = [n for n in (module_name(m) for m in modules) if n]
    if not names:
        raise ValueError("no module declaration found in the uploaded files")
    if top_module is not None:
        if top_module not in names:
            raise ValueError(f"top module {top_module!r} not found; saw {names}")
        return top_module
    if len(names) == 1:
        return names[0]
    # A module is a "top" candidate if no other module's body references it.
    by_name = {n: m for n, m in zip(names, modules)}
    candidates = []
    for n in names:
        others = "\n".join(b for k, b in by_name.items() if k != n)
        if not re.search(rf"\b{re.escape(n)}\b", others):
            candidates.append(n)
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        f"could not infer the top module among {names}; pass top_module explicitly "
        f"(uninstantiated candidates: {candidates or 'none'})"
    )


def build_clocked_testbench_template(
    interface: list[Port], stimulus: str, *, task_id: str = "uploaded"
) -> str:
    """Wrap a user-supplied scaffold-fill stimulus into a differential testbench template.

    The harness owns everything that makes the grade trustworthy — the dual
    instantiation of candidate (`__DUT__`) and reference (`__REF__`), the
    free-running clock, the output comparator (`rlhdl_sample`), and the
    `RESULT <passed> <total>` line the grader parses. The user supplies only
    `stimulus`: Verilog module-scope code that MUST define `task stimulus;`, drives
    the input ports by name, advances time with `@(posedge clk)`, and calls
    `rlhdl_sample;` at each point where candidate and reference outputs must agree.

    The returned string keeps the `__DUT__` / `__REF__` / `__TASK_ID__` placeholders
    so the existing `cologic.verifier.build_testbench` substitution path applies
    unchanged.
    """
    inputs = [p for p in interface if p.direction == "input"]
    outputs = [p for p in interface if p.direction == "output"]
    if not outputs:
        raise ValueError("design has no output ports to compare")
    clk = next((p for p in inputs if p.name.lower() in _CLOCK_NAMES), None)
    if clk is None:
        raise ValueError(
            "scaffold-fill needs a clock port named clk/clock; none found in the interface"
        )
    if not re.search(r"\btask\s+stimulus\b", stimulus):
        raise ValueError(
            "stimulus must define `task stimulus;` (the entry point the harness calls)"
        )

    def width(p: Port) -> str:
        return "" if p.width == 1 else f"[{p.width - 1}:0] "

    decls = []
    for p in inputs:
        init = " = 0" if p is clk else ""
        decls.append(f"  logic {width(p)}{p.name}{init};")
    for p in outputs:
        decls.append(f"  logic {width(p)}{p.name}__c;")
        decls.append(f"  logic {width(p)}{p.name}__r;")

    def conn(suffix: str) -> str:
        parts = [f".{p.name}({p.name})" for p in inputs]
        parts += [f".{p.name}({p.name}{suffix})" for p in outputs]
        return ", ".join(parts)

    compare = "\n".join(
        f"      rlhdl_total += 1; if ({p.name}__c === {p.name}__r) rlhdl_pass += 1;"
        for p in outputs
    )
    user_body = textwrap.indent(textwrap.dedent(stimulus).strip("\n"), "  ")

    return f"""// scaffold-fill differential testbench for task __TASK_ID__
module tb;
{chr(10).join(decls)}

  __DUT__ dut_c ({conn("__c")});
  __REF__ dut_r ({conn("__r")});

  always #5 {clk.name} = ~{clk.name};

  integer rlhdl_pass = 0;
  integer rlhdl_total = 0;

  // Compare every candidate output against the reference. Call from `stimulus`
  // whenever the two designs should agree (typically after a settling edge).
  task rlhdl_sample;
    begin
{compare}
    end
  endtask

  // ===== user scaffold-fill (must define `task stimulus;`) =====
{user_body}
  // ===== end scaffold-fill =====

  initial begin
    stimulus;
    $display("RESULT %0d %0d", rlhdl_pass, rlhdl_total);
    $finish;
  end
endmodule
"""


def task_from_upload(
    files: dict[str, str],
    *,
    prompt: str,
    stimulus: str | None = None,
    top_module: str | None = None,
    interface: list[Port] | None = None,
    task_id: str = "uploaded",
    n_vectors: int = 256,
    seed: int = 1,
) -> Task:
    """Build a gradeable Task from the upload flow: many Verilog files + a prompt.

    Clocked designs (a clock-like port present) REQUIRE a scaffold-fill `stimulus`;
    it becomes the differential testbench template. Combinational designs ignore
    `stimulus` and grade through the auto-generated random-vector testbench. The
    `prompt` textbox becomes the Task spec (what the optimizer is told to do).

    `interface` overrides the parsed ports for headers the parser can't handle.
    """
    rtl = concat_files(files)
    top = resolve_top(rtl, top_module)
    ports = interface if interface is not None else parse_interface(rtl, top)[1]
    clocked = is_clocked(ports)

    tb_template: str | None = None
    if clocked:
        if not stimulus or not stimulus.strip():
            raise ValueError(
                "this is a clocked design — provide a scaffold-fill stimulus "
                "(defining `task stimulus;`)"
            )
        tb_template = build_clocked_testbench_template(ports, stimulus, task_id=task_id)

    return Task(
        task_id=task_id,
        top_module=top,
        spec=prompt,
        interface=ports,
        reference_rtl=rtl,
        n_vectors=n_vectors,
        seed=seed,
        clocked=clocked,
        testbench_template=tb_template,
        allow_extra_modules=len(extract_modules(rtl)) > 1,
        tags=["uploaded"],
    )


# Default spec when a manifest entry doesn't carry its own.
DEFAULT_OPTIMIZE_SPEC = (
    "Optimize this Verilog module for gate count while preserving its function."
)


def task_from_manifest_entry(
    entry: dict, base_dir, *, default_spec: str = DEFAULT_OPTIMIZE_SPEC
) -> Task:
    """Build a Task from one dataset manifest entry — the SHARED loader the SIA
    target agent and evaluate.py both call so they can never drift.

    Entry schema (all but `id` + `file`/`files` optional):
      id          : design id (becomes task_id, submission filename)
      file        : one RTL path, relative to base_dir
      files       : OR a list of RTL paths (hierarchical design)
      stimulus_file / stimulus : scaffold-fill stimulus (path or inline) — REQUIRED
                    for clocked designs (defines `task stimulus;`)
      top_module  : explicit top (else inferred)
      ports       : explicit interface [{name, direction, width}] (else parsed)
      spec        : per-design optimize prompt (else `default_spec`)
      n_vectors, seed : grading vector count / seed

    Reuses task_from_upload, so clocked designs route through the differential
    scaffold testbench exactly like a web upload.
    """
    from pathlib import Path

    base = Path(base_dir)
    paths = entry["files"] if entry.get("files") else [entry["file"]]
    files = {Path(p).name: (base / p).read_text() for p in paths}

    stimulus = None
    if entry.get("stimulus_file"):
        stimulus = (base / entry["stimulus_file"]).read_text()
    elif entry.get("stimulus"):
        stimulus = entry["stimulus"]

    interface = [Port(**p) for p in entry["ports"]] if entry.get("ports") else None
    return task_from_upload(
        files,
        prompt=entry.get("spec") or default_spec,
        stimulus=stimulus,
        top_module=entry.get("top_module"),
        interface=interface,
        task_id=entry["id"],
        n_vectors=entry.get("n_vectors", 256),
        seed=entry.get("seed", 1),
    )


def write_upload_dataset(public_dir, upload: dict) -> dict:
    """Materialize an uploaded design as a SIA public dataset and return its entry.

    Writes `designs/<files>` (+ `designs/<id>_stim.sv` for clocked designs) and a
    one-entry `manifest.json` that `task_from_manifest_entry` reads back. This is the
    inverse of that loader — kept here so the manifest schema lives in one place.

    `upload` keys: id, files {name: content}, stimulus?, top_module?, prompt?,
    n_vectors?, seed?.
    """
    import json
    import shutil
    from pathlib import Path

    public = Path(public_dir)
    designs = public / "designs"
    if designs.exists():
        shutil.rmtree(designs)
    designs.mkdir(parents=True, exist_ok=True)

    rels = []
    for name, content in upload["files"].items():
        (designs / name).write_text(content)
        rels.append(f"designs/{name}")

    entry: dict = {
        "id": upload["id"],
        "n_vectors": upload.get("n_vectors", 256),
        "seed": upload.get("seed", 1),
    }
    entry["file" if len(rels) == 1 else "files"] = rels[0] if len(rels) == 1 else rels
    if upload.get("top_module"):
        entry["top_module"] = upload["top_module"]
    if upload.get("prompt"):
        entry["spec"] = upload["prompt"]
    if upload.get("stimulus"):
        (designs / f"{upload['id']}_stim.sv").write_text(upload["stimulus"])
        entry["stimulus_file"] = f"designs/{upload['id']}_stim.sv"

    (public / "manifest.json").write_text(json.dumps({"designs": [entry]}, indent=2) + "\n")
    return entry
