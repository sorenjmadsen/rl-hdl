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


def _entries() -> list[dict]:
    return json.loads((PUBLIC / "manifest.json").read_text())["designs"]


def evaluate(gen_dir: Path) -> dict:
    import modal

    from cologic.upload import task_from_manifest_entry

    # The immutable verifier (Verilator + Yosys) is the deployed Modal function —
    # we never carry the toolchain here; we call it by name.
    grader = modal.Function.from_name("rl-hdl", "grade_opt_remote")
    sub_dir = gen_dir / "submission"
    designs = []
    entries = _entries()
    print(f"[EVAL] scoring {len(entries)} submitted designs via the deployed verifier", flush=True)
    for e in entries:
        # SHARED loader (clocked-aware) — must match the target agent exactly.
        task = task_from_manifest_entry(e, PUBLIC)
        f = sub_dir / f"{e['id']}.v"
        if not f.exists():
            print(f"[EVAL] {e['id']}: no submission (missing)", flush=True)
            designs.append({"id": e["id"], "reward": 0.0, "stage": "missing",
                            "equivalent": False, "ref_cells": None, "cand_cells": None,
                            "area_improvement": None, "ref_area_um2": None,
                            "cand_area_um2": None, "area_um2_improvement": None})
            continue
        gr = grader.remote(f.read_text(), task)  # {"reward", "info", "task_id"}
        i = gr["info"]
        cells = (f"{i.get('ref_cells')}->{i.get('cand_cells')}"
                 if i.get("cand_cells") is not None else "n/a")
        ai = i.get("area_improvement")
        ai_s = f" ({ai * 100:+.1f}%)" if ai is not None else ""
        print(f"[EVAL] {e['id']}: equiv={bool(i.get('equivalent'))} cells {cells}{ai_s} "
              f"reward={gr['reward']:.3f}", flush=True)
        designs.append({
            "id": e["id"], "reward": gr["reward"], "stage": i.get("stage"),
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
    summary = {
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
    print(f"[FOOTPRINT] generation: mean_area_improvement="
          f"{summary['mean_area_improvement'] * 100:+.1f}% "
          f"equiv={summary['n_equivalent']}/{summary['n_total']} "
          f"mean_reward={summary['mean_reward']:.3f}", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-dir", type=Path, required=True)
    args = ap.parse_args()
    results = evaluate(args.gen_dir)
    (args.gen_dir / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
