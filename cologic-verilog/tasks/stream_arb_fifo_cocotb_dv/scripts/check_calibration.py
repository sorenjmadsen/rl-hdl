#!/usr/bin/env python3

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRADE_PATH = ROOT / "donotaccess" / "grade.py"


def load_grade_module():
    spec = importlib.util.spec_from_file_location("stream_arb_fifo_cocotb_grade", GRADE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {GRADE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    grade_mod = load_grade_module()
    cases = [
        (
            "starter_testbench",
            ROOT / "dv" / "cocotb" / "test_stream_arb_fifo.py",
            0.25,
        ),
        (
            "reference_solution",
            ROOT / "donotaccess" / "solution" / "test_stream_arb_fifo.py",
            1.0,
        ),
    ]
    ok = True
    for name, tests, expected in cases:
        result = grade_mod.grade(ROOT, test_override=tests)
        reward = float(result["reward"])
        print(f"{name}: reward={reward:.6f} expected={expected:.6f}")
        if abs(reward - expected) > 0.000001:
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
