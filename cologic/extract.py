"""Robust extraction of a Verilog module from raw LLM output.

Models wrap code in ```verilog fences, add prose, emit multiple modules, or
forget fences entirely. We want the module the task asked for, but fall back
gracefully so a near-miss still reaches the compiler (and earns partial credit).
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"```(?:systemverilog|verilog|sv|v)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
# A module body: `module ... endmodule`, non-greedy so we capture each one.
_MODULE = re.compile(r"\bmodule\b.*?\bendmodule\b", re.DOTALL)
_MODULE_NAME = re.compile(r"\bmodule\s+([A-Za-z_]\w*)")


def extract_modules(text: str) -> list[str]:
    """Return every `module ... endmodule` block found in the text.

    Prefers content inside code fences (strips prose), but if fences yield no
    module it scans the whole text so an unfenced answer still counts.
    """
    candidates: list[str] = []
    fenced = "\n".join(_FENCE.findall(text))
    if _MODULE.search(fenced or ""):
        candidates = _MODULE.findall(fenced)
    if not candidates:
        candidates = _MODULE.findall(text)
    return [c.strip() for c in candidates]


def extract_module(text: str, top_module: str | None = None) -> str | None:
    """Pick the single module to grade.

    If `top_module` is given and present, return that one. Otherwise return the
    last module found (models often write helpers first, the answer last).
    Returns None if no module is present at all.
    """
    modules = extract_modules(text)
    if not modules:
        return None
    if top_module:
        for m in modules:
            name = _MODULE_NAME.search(m)
            if name and name.group(1) == top_module:
                return m
    return modules[-1]


def module_name(verilog: str) -> str | None:
    m = _MODULE_NAME.search(verilog)
    return m.group(1) if m else None


def rename_module(verilog: str, old: str, new: str) -> str:
    """Rename the module declaration `module old` -> `module new`.

    Used to make a `_ref` copy of the reference so candidate and reference can be
    compiled into one testbench without a name collision. Only the declaration is
    touched (a leaf module never instantiates itself).
    """
    return re.sub(rf"\bmodule\s+{re.escape(old)}\b", f"module {new}", verilog, count=1)
