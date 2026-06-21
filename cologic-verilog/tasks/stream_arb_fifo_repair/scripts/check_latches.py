#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_latches.py <proc-json>", file=sys.stderr)
        return 2

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    latch_count = 0
    for module in data.get("modules", {}).values():
        for cell in module.get("cells", {}).values():
            if cell.get("type") == "$dlatch":
                latch_count += 1

    print(f"latch_count={latch_count}")
    return 0 if latch_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
