"""Reference target agent: a self-contained RTL optimizer (the harness SIA evolves).

Seeded from harness/optimizer.py but INLINED here so SIA's Feedback-Agent can
rewrite the whole scaffold — strategies, sampling schedule, repair budget,
candidate selection — across generations. SIA mutates only this file.

Contract (set by SIA):
    python target_agent.py --dataset_dir <data/public> --working_dir <gen_dir>

For each design in <dataset_dir>/manifest.json it reads the baseline RTL, samples
structural rewrites from the policy model, self-checks each with the IMMUTABLE
grader (cologic.grader — equivalence + Yosys PPA; used here only to RANK its own
candidates), repairs ones that broke equivalence, and writes the best module to
<working_dir>/submission/<id>.v. The official reward is recomputed independently
by evaluate.py — this agent cannot fake it.

Design is read from FILES (works for any uploaded Verilog), and the interface is
parsed from the RTL via cologic.upload.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

import modal
from openai import OpenAI

from cologic.extract import extract_module
from cologic.upload import task_from_manifest_entry

# The immutable verifier (Verilator + Yosys) is the DEPLOYED Modal function. We
# use it only to RANK our own candidates; the official reward is recomputed by
# evaluate.py. This agent carries no silicon toolchain.
_grader = modal.Function.from_name("rl-hdl", "grade_opt_remote")


def _log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


# ===========================================================================
# IF YOU ARE REVISING THIS AGENT: grading goes through the DEPLOYED verifier
# (`_grader` = grade_opt_remote) and NOTHING ELSE. There is no local Verilator or
# Yosys here. DO NOT replace this with an LLM equivalence check, an area estimate,
# or a "grader unavailable -> assume equivalent" fallback — the official score is
# recomputed by evaluate.py with this same verifier, so any guess scores nothing.
# Keep grade() as the only way candidates are checked. Fail loudly on errors.
# ===========================================================================
def grade(rtl: str, task, label: str = "") -> SimpleNamespace:
    # A grade IS a simulation: the deployed verifier runs Verilator (equivalence)
    # then Yosys (gate count). Log the trigger and the footprint it reports back.
    _log("SIM", f"{task.task_id} {label}: verifying on the deployed Modal grader (Verilator + Yosys)")
    out = _grader.remote(rtl, task)  # {"reward", "info", "task_id"} — raises on failure (no fallback)
    r = SimpleNamespace(reward=out["reward"], info=out["info"])
    i = r.info
    cells = (f"{i.get('ref_cells')}->{i.get('cand_cells')}"
             if i.get("cand_cells") is not None else "n/a")
    ai = i.get("area_improvement")
    ai_s = f" ({ai * 100:+.1f}%)" if ai is not None else ""
    _log("FOOTPRINT", f"{task.task_id} {label}: equiv={i.get('equivalent')} "
                      f"cells {cells}{ai_s} reward={r.reward:.3f}")
    return r

# ── Policy model (injected via env; defaults to the Cologic Fireworks deployment) ──
MODEL = os.environ.get("COLOGIC_TARGET_MODEL", "accounts/fireworks/models/kimi-k2p7-code")
_client = OpenAI(
    api_key=os.environ.get("FIREWORKS_API_KEY"),
    base_url=os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
    max_retries=6,
)

# ── Knobs (the harness search space SIA tunes) ──
N_CANDIDATES = int(os.environ.get("COLOGIC_N_CANDIDATES", "6"))
TEMPERATURE = float(os.environ.get("COLOGIC_TEMPERATURE", "0.9"))
MAX_REPAIR_ROUNDS = int(os.environ.get("COLOGIC_MAX_REPAIR", "1"))
MAX_TOKENS = int(os.environ.get("COLOGIC_MAX_TOKENS", "2048"))

# Structural-rewrite menu. The biggest synth-surviving wins are arithmetic-structural
# (sharing operators under selects, removing redundant arithmetic, strength reduction).
STRATEGIES = [
    "Share arithmetic operators under mutually-exclusive selects: compute one of "
    "several products/sums with a single multiplier/adder and mux the operands, "
    "instead of instantiating one per branch.",
    "Remove redundant or duplicated arithmetic; fold constants.",
    "Strength-reduce: replace multiplies/divides by constants with shifts and adds.",
    "Simplify/flatten case and if-else chains into a compact equivalent form.",
    "Restructure the datapath into a smaller but equivalent form.",
]

SYSTEM_REWRITE = (
    "You are an expert hardware engineer. You are given a CORRECT Verilog module and must "
    "rewrite it to use FEWER gates while preserving EXACT functional equivalence. Keep the "
    "module name, port names, directions, and widths identical. Respond with exactly one "
    "Verilog module in a single ```verilog code block — no prose."
)
SYSTEM_REPAIR = (
    "You are an expert hardware engineer. Your previous rewrite was rejected by the "
    "equivalence checker. Fix it so it is exactly equivalent to the original while staying "
    "as small as you can. Keep the module name and interface identical. Respond with exactly "
    "one Verilog module in a single ```verilog code block — no prose."
)


def _chat(messages: list[dict]) -> str:
    resp = _client.chat.completions.create(
        model=MODEL, messages=messages, temperature=TEMPERATURE, top_p=0.95, max_tokens=MAX_TOKENS,
    )
    return resp.choices[0].message.content or ""


def _rewrite_msgs(task, strategy: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_REWRITE},
        {"role": "user", "content": (
            f"Optimize this module for gate count. Apply this strategy where it helps:\n  {strategy}\n\n"
            f"```verilog\n{task.reference_rtl}\n```\n\n"
            f"Return the optimized module `{task.top_module}` with the same name and interface."
        )},
    ]


def _repair_msgs(task, candidate: str, info: dict) -> list[dict]:
    p, t = info.get("eq_passed", 0), info.get("eq_total", 0)
    why = ("it did not compile:\n" + info.get("log", "")[:600]) if info.get("stage") == "compile_error" \
        else f"it compiles but is NOT equivalent — {t - p}/{t} output-vector comparisons mismatch."
    return [
        {"role": "system", "content": SYSTEM_REPAIR},
        {"role": "user", "content": (
            f"Original (correct) module:\n\n```verilog\n{task.reference_rtl}\n```\n\n"
            f"Your rewrite was rejected: {why}\n\n"
            f"Your rejected rewrite:\n\n```verilog\n{candidate}\n```\n\n"
            f"Return a corrected, equivalent module with the same name and interface."
        )},
    ]


def optimize_one(task) -> tuple[str, dict, list[dict]]:
    """Return (best_rtl, best_info, candidate_log) for one design."""
    _log("HARNESS", f"optimizing {task.task_id}: baseline + {N_CANDIDATES} rewrites "
                    f"(temp={TEMPERATURE}, repair<= {MAX_REPAIR_ROUNDS})")
    best_rtl = task.reference_rtl
    best = grade(best_rtl, task, "baseline")
    log = [{"origin": "baseline", "reward": best.reward, "stage": best.info.get("stage"),
            "equivalent": bool(best.info.get("equivalent"))}]

    for i in range(N_CANDIDATES):
        strategy = STRATEGIES[i % len(STRATEGIES)]
        _log("HARNESS", f"{task.task_id}: sampling rewrite {i} — {strategy[:48]}...")
        cand = _chat(_rewrite_msgs(task, strategy))
        r = grade(cand, task, f"rewrite{i}")
        rounds = 0
        while rounds < MAX_REPAIR_ROUNDS and r.info.get("compiled") and not r.info.get("equivalent"):
            rounds += 1
            _log("HARNESS", f"{task.task_id}: rewrite {i} broke equivalence — repair {rounds}")
            cand = _chat(_repair_msgs(task, cand, r.info))
            r = grade(cand, task, f"rewrite{i}+repair{rounds}")
        log.append({"origin": f"rewrite{i}", "reward": r.reward, "stage": r.info.get("stage"),
                    "equivalent": bool(r.info.get("equivalent"))})
        if r.reward > best.reward:
            best, best_rtl = r, cand

    ai = best.info.get("area_improvement")
    ai_s = f"{ai * 100:+.1f}%" if ai is not None else "n/a"
    _log("RESULT", f"{task.task_id}: best equiv={best.info.get('equivalent')} "
                   f"footprint={ai_s} reward={best.reward:.3f}")
    return best_rtl, best.info, log


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_dir", required=True)
    ap.add_argument("--working_dir", required=True)
    args = ap.parse_args()

    dataset_dir, working_dir = Path(args.dataset_dir), Path(args.working_dir)
    submission = working_dir / "submission"
    submission.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    trajectory = []
    for entry in manifest["designs"]:
        # SHARED loader (clocked-aware) — matches evaluate.py so the task we
        # optimize is exactly the task we're scored on.
        task = task_from_manifest_entry(entry, dataset_dir)
        best_rtl, info, log = optimize_one(task)
        module = extract_module(best_rtl, task.top_module) or best_rtl
        (submission / f"{entry['id']}.v").write_text(module.strip() + "\n")
        trajectory.append({"id": entry["id"], "best_reward": info.get("reward"),
                           "stage": info.get("stage"), "equivalent": bool(info.get("equivalent")),
                           "area_improvement": info.get("area_improvement"), "candidates": log})
        print(f"{entry['id']}: stage={info.get('stage')} equiv={info.get('equivalent')} "
              f"area={info.get('area_improvement')}")

    (working_dir / "agent_execution.json").write_text(json.dumps(trajectory, indent=2))


if __name__ == "__main__":
    main()
