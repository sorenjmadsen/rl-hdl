"""Immutable reward bridge for the SIA RTL-optimize task.

SIA runs:  python evaluate.py --gen-dir <gen_dir>

For each design in this split's manifest, we build a Task from the (uploaded)
baseline RTL — parsing its interface — and grade the agent's submitted module with
the IMMUTABLE grader (Verilator equivalence + Yosys gate count). We write
`results.json`; SIA reads its top-level scalars as the self-improvement signal.

SIA only ever mutates `target_agent.py`. It never touches this file or the grader,
so reward cannot be gamed: a submission scores only if real silicon tooling
confirms it is equivalent and smaller. No LLM judge anywhere.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent  # .../data/public


def _designs() -> list[dict]:
    manifest = json.loads((PUBLIC / "manifest.json").read_text())
    out = []
    for e in manifest["designs"]:
        out.append({
            "id": e["id"],
            "rtl": (PUBLIC / e["file"]).read_text(),
            "top_module": e.get("top_module"),
            "ports": e.get("ports"),
            "n_vectors": e.get("n_vectors", 256),
            "seed": e.get("seed", 1),
        })
    return out


def evaluate(gen_dir: Path) -> dict:
    from cologic.grader import grade
    from cologic.schema import Port
    from cologic.upload import task_from_rtl

    sub_dir = gen_dir / "submission"
    designs = []
    for d in _designs():
        interface = [Port(**p) for p in d["ports"]] if d["ports"] else None
        task = task_from_rtl(
            d["rtl"], task_id=d["id"], top_module=d["top_module"],
            interface=interface, n_vectors=d["n_vectors"], seed=d["seed"],
        )
        f = sub_dir / f"{d['id']}.v"
        if not f.exists():
            designs.append({"id": d["id"], "reward": 0.0, "stage": "missing",
                            "equivalent": False, "ref_cells": None, "cand_cells": None,
                            "area_improvement": None, "ref_area_um2": None,
                            "cand_area_um2": None, "area_um2_improvement": None})
            continue
        r = grade(f.read_text(), task)
        i = r.info
        designs.append({
            "id": d["id"], "reward": r.reward, "stage": i.get("stage"),
            "equivalent": bool(i.get("equivalent")),
            "ref_cells": i.get("ref_cells"), "cand_cells": i.get("cand_cells"),
            "area_improvement": i.get("area_improvement"),
            # Observe-only real silicon area (populated when a liberty lib is set).
            "ref_area_um2": i.get("ref_area_um2"),
            "cand_area_um2": i.get("cand_area_um2"),
            "area_um2_improvement": i.get("area_um2_improvement"),
        })

    rewards = [d["reward"] for d in designs]
    gains = [d["area_improvement"] for d in designs
             if d["equivalent"] and d["area_improvement"] is not None]
    um2_gains = [d["area_um2_improvement"] for d in designs
                 if d["equivalent"] and d["area_um2_improvement"] is not None]
    return {
        # Top-level scalars are the SIA self-improvement signal.
        "mean_reward": round(sum(rewards) / len(rewards), 6) if rewards else 0.0,
        "mean_area_improvement": round(sum(gains) / len(gains), 6) if gains else 0.0,
        # Observe-only: real-area signal alongside the cell-count one. NOT the
        # reward yet — mean_reward stays the optimization target.
        "mean_area_um2_improvement": round(sum(um2_gains) / len(um2_gains), 6) if um2_gains else 0.0,
        "n_equivalent": sum(d["equivalent"] for d in designs),
        "n_total": len(designs),
        "designs": designs,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-dir", type=Path, required=True)
    args = ap.parse_args()
    results = evaluate(args.gen_dir)
    (args.gen_dir / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
