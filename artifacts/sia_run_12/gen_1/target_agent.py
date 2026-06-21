"""Target agent: RTL optimizer using Fireworks/kimi-k2p7-code via OpenAI-compatible API.

Contract:
    python target_agent.py --dataset_dir <data/public> --working_dir <gen_dir>

For each design in <dataset_dir>/manifest.json, this agent:
  1. Reads the baseline RTL.
  2. Samples structural rewrites from the policy model (Fireworks kimi-k2p7-code).
  3. Self-checks each candidate with the IMMUTABLE deployed Modal grader
     (Verilator equivalence + Yosys gate count).
  4. Repairs candidates that broke equivalence.
  5. Writes the best verified module to <working_dir>/submission/<id>.v.

Verification is ALWAYS done via grade_opt_remote (the deployed Modal function).
No LLM-based equivalence check, no guesses, no fallbacks — fail loudly on error.
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
from cologic.schema import Port
from cologic.upload import task_from_rtl

# ---------------------------------------------------------------------------
# Immutable verifier: the ONLY way candidates are checked. Do not replace
# this with LLM checks, estimates, or "assume equivalent" fallbacks.
# ---------------------------------------------------------------------------
_grader = modal.Function.from_name("rl-hdl", "grade_opt_remote")


def _log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def grade(rtl: str, task, label: str = "") -> SimpleNamespace:
    """Grade a candidate via the deployed Modal verifier (Verilator + Yosys).

    Raises on any failure — no fallback, no silent suppression.
    """
    _log("SIM", f"{task.task_id} {label}: submitting to Modal grader (Verilator + Yosys)")
    out = _grader.remote(rtl, task)  # raises on failure — intentional
    r = SimpleNamespace(reward=out["reward"], info=out["info"])
    i = r.info
    cells_str = (
        f"{i.get('ref_cells')}->{i.get('cand_cells')}"
        if i.get("cand_cells") is not None
        else "n/a"
    )
    ai = i.get("area_improvement")
    ai_s = f" ({ai * 100:+.1f}%)" if ai is not None else ""
    _log(
        "FOOTPRINT",
        f"{task.task_id} {label}: equiv={i.get('equivalent')} "
        f"cells {cells_str}{ai_s} reward={r.reward:.3f}",
    )
    return r


# ---------------------------------------------------------------------------
# Policy model — OpenAI-compatible Fireworks endpoint
# ---------------------------------------------------------------------------
MODEL = os.environ.get("COLOGIC_TARGET_MODEL", "accounts/fireworks/models/kimi-k2p7-code")

_client = OpenAI(
    base_url=os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
    api_key=os.environ.get("FIREWORKS_API_KEY"),
    max_retries=6,
)

# ---------------------------------------------------------------------------
# Tunable knobs
# ---------------------------------------------------------------------------
N_CANDIDATES = int(os.environ.get("COLOGIC_N_CANDIDATES", "6"))
TEMPERATURE = float(os.environ.get("COLOGIC_TEMPERATURE", "0.9"))
MAX_REPAIR_ROUNDS = int(os.environ.get("COLOGIC_MAX_REPAIR", "2"))
MAX_TOKENS = int(os.environ.get("COLOGIC_MAX_TOKENS", "4096"))

# ---------------------------------------------------------------------------
# Rewrite strategies (synth-surviving arithmetic-structural wins)
# ---------------------------------------------------------------------------
STRATEGIES = [
    "Share arithmetic operators under mutually-exclusive selects: replace "
    "two separate multipliers/adders used in an if-else or ternary with a "
    "single shared operator whose operands are muxed before the operation.",
    "Remove redundant or duplicated arithmetic subexpressions; fold "
    "compile-time constants into simpler expressions.",
    "Strength-reduce constant multiplies and divides to shifts and adds "
    "(e.g., x*8 -> x<<3, x*5 -> (x<<2)+x).",
    "Simplify and flatten cascaded case/if-else chains into a minimal "
    "equivalent combinational expression.",
    "Restructure the datapath to share intermediate results and reduce "
    "the total operator count while preserving exact functional equivalence.",
    "Identify and eliminate dead code; merge equivalent branches; "
    "reduce unnecessary intermediate registers where combinational is enough.",
]

SYSTEM_REWRITE = (
    "You are an expert hardware engineer specialising in RTL optimisation. "
    "You are given a CORRECT Verilog module. Rewrite it to use FEWER gates "
    "while preserving EXACT functional equivalence. "
    "Keep the module name, port names, port directions, and port widths IDENTICAL. "
    "Respond with exactly one Verilog module inside a single ```verilog code block — no prose."
)

SYSTEM_REPAIR = (
    "You are an expert hardware engineer. Your previous Verilog rewrite was rejected "
    "by the equivalence checker. Fix it so that it is EXACTLY equivalent to the "
    "original module while keeping it as small as possible. "
    "Keep the module name and interface IDENTICAL to the original. "
    "Respond with exactly one Verilog module inside a single ```verilog code block — no prose."
)


def _chat(messages: list[dict], trajectory_log: list) -> str:
    """Call the model and record the turn in trajectory_log."""
    resp = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        top_p=0.95,
        max_tokens=MAX_TOKENS,
    )
    content = resp.choices[0].message.content or ""

    # Log this turn (no cost — per-provider pricing unknown)
    trajectory_log.append({
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "usage": {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
            "total_tokens": resp.usage.total_tokens if resp.usage else None,
            "cost_usd": 0,  # per-provider pricing unknown
        },
    })
    return content


def _push_user(messages: list[dict], trajectory_log: list, content: str) -> None:
    """Append a user message to both the running messages list and the log."""
    messages.append({"role": "user", "content": content})
    trajectory_log.append({"role": "user", "content": [{"type": "text", "text": content}]})


def _rewrite_prompt(task, strategy: str, dataset_dir: str, working_dir: str) -> str:
    return (
        f"Dataset directory (READ-ONLY): {dataset_dir}\n"
        f"Working directory (READ-WRITE): {working_dir}\n\n"
        f"Optimize the following module for gate count. "
        f"Apply this strategy where it helps:\n  {strategy}\n\n"
        f"```verilog\n{task.reference_rtl}\n```\n\n"
        f"Return the optimized module `{task.top_module}` with the SAME name and interface."
    )


def _repair_prompt(task, candidate: str, info: dict, dataset_dir: str, working_dir: str) -> str:
    p = info.get("eq_passed", 0)
    t = info.get("eq_total", 0)
    if info.get("stage") == "compile_error":
        why = "it did not compile:\n" + info.get("log", "")[:600]
    else:
        why = f"it compiles but is NOT equivalent — {t - p}/{t} output-vector comparisons mismatch."

    return (
        f"Dataset directory (READ-ONLY): {dataset_dir}\n"
        f"Working directory (READ-WRITE): {working_dir}\n\n"
        f"Original (correct) module:\n\n```verilog\n{task.reference_rtl}\n```\n\n"
        f"Your rewrite was rejected: {why}\n\n"
        f"Your rejected rewrite:\n\n```verilog\n{candidate}\n```\n\n"
        f"Return a corrected, equivalent module with the SAME name and interface."
    )


def optimize_one(
    task, dataset_dir: str, working_dir: str
) -> tuple[str, dict, list[dict]]:
    """Return (best_rtl, best_info, trajectory) for one design."""
    _log(
        "HARNESS",
        f"optimizing {task.task_id}: baseline + {N_CANDIDATES} rewrites "
        f"(temp={TEMPERATURE}, repair<={MAX_REPAIR_ROUNDS})",
    )

    trajectory: list[dict] = []

    # System messages are recorded once per design session
    system_msg = {"role": "system", "content": [{"type": "text", "text": SYSTEM_REWRITE}]}
    trajectory.append(system_msg)

    # Grade baseline
    best_result = grade(task.reference_rtl, task, "baseline")
    best_rtl = task.reference_rtl
    candidate_log = [
        {
            "origin": "baseline",
            "reward": best_result.reward,
            "stage": best_result.info.get("stage"),
            "equivalent": bool(best_result.info.get("equivalent")),
            "area_improvement": best_result.info.get("area_improvement"),
        }
    ]

    for i in range(N_CANDIDATES):
        strategy = STRATEGIES[i % len(STRATEGIES)]
        _log("HARNESS", f"{task.task_id}: sampling rewrite {i} — {strategy[:60]}...")

        # Build messages list for this candidate (fresh conversation each time)
        messages: list[dict] = [{"role": "system", "content": SYSTEM_REWRITE}]
        user_text = _rewrite_prompt(task, strategy, dataset_dir, working_dir)
        _push_user(messages, trajectory, user_text)

        cand = _chat(messages, trajectory)
        # Add assistant reply to running messages for potential repair
        messages.append({"role": "assistant", "content": cand})

        r = grade(cand, task, f"rewrite{i}")
        rounds = 0

        # Repair loop — only if it compiled but isn't equivalent
        while (
            rounds < MAX_REPAIR_ROUNDS
            and r.info.get("compiled")
            and not r.info.get("equivalent")
        ):
            rounds += 1
            _log("HARNESS", f"{task.task_id}: rewrite {i} not equivalent — repair {rounds}")
            # Switch to repair system prompt
            messages[0] = {"role": "system", "content": SYSTEM_REPAIR}
            repair_text = _repair_prompt(task, cand, r.info, dataset_dir, working_dir)
            _push_user(messages, trajectory, repair_text)
            cand = _chat(messages, trajectory)
            messages.append({"role": "assistant", "content": cand})
            r = grade(cand, task, f"rewrite{i}+repair{rounds}")

        entry = {
            "origin": f"rewrite{i}",
            "reward": r.reward,
            "stage": r.info.get("stage"),
            "equivalent": bool(r.info.get("equivalent")),
            "area_improvement": r.info.get("area_improvement"),
        }
        candidate_log.append(entry)

        if r.reward > best_result.reward:
            best_result, best_rtl = r, cand

    ai = best_result.info.get("area_improvement")
    ai_s = f"{ai * 100:+.1f}%" if ai is not None else "n/a"
    _log(
        "RESULT",
        f"{task.task_id}: best equiv={best_result.info.get('equivalent')} "
        f"area={ai_s} reward={best_result.reward:.3f}",
    )
    return best_rtl, best_result.info, trajectory, candidate_log


def main() -> None:
    ap = argparse.ArgumentParser(description="RTL optimizer using kimi-k2p7-code via Fireworks")
    ap.add_argument("--dataset_dir", required=True, help="Read-only dataset directory")
    ap.add_argument("--working_dir", required=True, help="Read-write working directory")
    args = ap.parse_args()

    dataset_dir = Path(args.dataset_dir)
    working_dir = Path(args.working_dir)

    submission_dir = working_dir / "submission"
    submission_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    overall_trajectory: list[dict] = []

    for entry in manifest["designs"]:
        design_id = entry["id"]
        rtl = (dataset_dir / entry["file"]).read_text()
        interface = (
            [Port(**p) for p in entry["ports"]] if entry.get("ports") else None
        )
        task = task_from_rtl(
            rtl,
            task_id=design_id,
            top_module=entry.get("top_module"),
            interface=interface,
            n_vectors=entry.get("n_vectors", 256),
            seed=entry.get("seed", 1),
        )

        best_rtl, info, trajectory, candidate_log = optimize_one(
            task, str(dataset_dir), str(working_dir)
        )

        # Extract clean module text
        module = extract_module(best_rtl, task.top_module) or best_rtl
        (submission_dir / f"{design_id}.v").write_text(module.strip() + "\n")

        overall_trajectory.append(
            {
                "design_id": design_id,
                "trajectory": trajectory,
                "summary": {
                    "best_reward": info.get("reward"),
                    "stage": info.get("stage"),
                    "equivalent": bool(info.get("equivalent")),
                    "area_improvement": info.get("area_improvement"),
                    "candidates": candidate_log,
                },
            }
        )

        print(
            f"{design_id}: stage={info.get('stage')} "
            f"equiv={info.get('equivalent')} "
            f"area={info.get('area_improvement')}",
            flush=True,
        )

    # Save execution log (single file — one optimisation run across all designs)
    (working_dir / "agent_execution.json").write_text(
        json.dumps(overall_trajectory, indent=2)
    )
    _log("DONE", f"Processed {len(manifest['designs'])} design(s). "
                  f"Outputs in {submission_dir}")


if __name__ == "__main__":
    main()
