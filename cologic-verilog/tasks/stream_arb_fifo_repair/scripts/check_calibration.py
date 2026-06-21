#!/usr/bin/env python3

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRADE_PATH = ROOT / "donotaccess" / "grade.py"


def load_grade_module():
    spec = importlib.util.spec_from_file_location("stream_arb_fifo_grade", GRADE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {GRADE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    grade_mod = load_grade_module()
    cases = [
        ("buggy_baseline", None, 0.0),
        ("golden_reference", ROOT / "donotaccess" / "stream_arb_fifo_golden.sv", 1.0),
        (
            "functional_fixed_latch_remaining",
            ROOT / "donotaccess" / "variants" / "stream_arb_fifo_latch_only.sv",
            0.7,
        ),
    ]

    ok = True
    for name, rtl, expected in cases:
        result = grade_mod.grade(ROOT, rtl, ROOT / "donotaccess")
        reward = float(result["reward"])
        print(f"{name}: reward={reward:.3f} expected={expected:.3f}")
        if abs(reward - expected) > 1e-6:
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
