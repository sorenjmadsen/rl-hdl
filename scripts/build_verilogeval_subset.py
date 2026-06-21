"""Convert a local VerilogEval clone into the committed combinational subset JSON.

Usage:
  git clone --depth 1 https://github.com/NVlabs/verilog-eval.git data/verilog-eval
  uv run python scripts/build_verilogeval_subset.py
"""

from __future__ import annotations

import json
from pathlib import Path

from cologic.datasets.verilogeval import convert_dir

SRC = Path("data/verilog-eval/dataset_spec-to-rtl")
OUT = Path("cologic/datasets/verilogeval_combinational.json")


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"clone VerilogEval first: {SRC} not found")
    records = convert_dir(SRC)
    OUT.write_text(json.dumps(records, indent=1))
    print(f"wrote {OUT} with {len(records)} combinational problems")
    widths = sorted({p["width"] for r in records for p in r["interface"]})
    print(f"port widths seen: {widths}")


if __name__ == "__main__":
    main()
