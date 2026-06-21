"""Seed the SIA task's design files from cologic.designs (example 'uploads').

The task is FILE-DRIVEN so it works with any uploaded Verilog — this build tool
just seeds it with our curated examples. Train designs -> data/public,
held-out -> data/private. Re-run after changing cologic.designs.

    python sia_task/rtl-optimize/tools/build_designs.py
"""

from __future__ import annotations

import json
from pathlib import Path

from cologic.designs import HELDOUT_OPT_TASKS, TRAIN_OPT_TASKS

ROOT = Path(__file__).resolve().parents[1]  # sia_task/rtl-optimize/


def _emit(tasks, split_dir: Path) -> list[str]:
    designs_dir = split_dir / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for t in tasks:
        fname = f"{t.top_module}.v"
        (designs_dir / fname).write_text(t.reference_rtl)
        entries.append({
            "id": t.top_module,
            "file": f"designs/{fname}",
            "n_vectors": t.n_vectors,
            "seed": t.seed,
        })
    (split_dir / "manifest.json").write_text(json.dumps({"designs": entries}, indent=2) + "\n")
    return [e["id"] for e in entries]


def main() -> None:
    pub = _emit(TRAIN_OPT_TASKS, ROOT / "data" / "public")
    prv = _emit(HELDOUT_OPT_TASKS, ROOT / "data" / "private")
    print(f"public (train):   {pub}")
    print(f"private (heldout): {prv}")


if __name__ == "__main__":
    main()
