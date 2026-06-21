"""Target agent: RTL optimizer using Fireworks/kimi-k2p7-code via OpenAI-compatible API.

Generation 2 improvements over Gen 1:
1. FIXED repair loop: removed the `r.info.get("compiled")` guard so compile errors
   also receive repair attempts (previously, compile errors silently skipped repair).
2. Adaptive hill climbing: if a candidate improves best_rtl, subsequent candidates
   build on that improved version (refinement) rather than starting from baseline.
3. Comprehensive first strategy: circuit-aware prompt covering all major optimization
   patterns (mux-of-multipliers, popcount, raw multiplier, mux tree, strength reduction)
   so the model picks the most relevant one per circuit.
4. Direct/clean-rewrite as strategy 1: "just write it simply" often beats complex
   structural rewrites because the synthesizer can optimize clean code better.
5. Clean RTL in prompts: extract_module() strips markdown before including in refine
   prompts to avoid double-wrapping.
6. Fresh messages for repair (reference style): avoids context contamination.

Contract:
    python target_agent.py --dataset_dir <data/public> --working_dir <gen_dir>

For each design in manifest.json: read baseline RTL, sample rewrites from the policy
model, check each with the IMMUTABLE deployed Modal grader (Verilator + Yosys),
repair failures, write the best verified module to submission/<id>.v.

Verification is ALWAYS done via grade_opt_remote. No LLM equivalence checks. Fail
loudly on grader errors — no fallbacks.
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
# Immutable verifier: the ONLY way candidates are checked.
# DO NOT replace with LLM checks, estimates, or "assume equivalent" fallbacks.
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
# Rewrite strategies
#
# Strategy ordering matters most when N_CANDIDATES is small (e.g., 2).
# Strategy 0 is a broad "circuit-aware" prompt that works across all types.
# Strategy 1 is a "direct clean rewrite" that complements strategy 0.
# Strategies 2+ are more specific fallbacks for larger candidate budgets.
# ---------------------------------------------------------------------------
STRATEGIES = [
    # Strategy 0: Circuit-aware analysis — broad, works for any circuit type.
    # The model analyzes what kind of circuit it is and picks the right technique.
    (
        "Analyze the circuit and apply the single most impactful structural optimization:\n"
        "  (a) If it MUXes two separate arithmetic operations on a shared select, merge into\n"
        "      ONE operator with muxed operands: y = (s?a:c) * (s?b:d) instead of two ops.\n"
        "  (b) If it counts set bits (popcount), rewrite as an explicit binary adder tree:\n"
        "      layer-1 adds pairs, layer-2 adds layer-1 outputs, etc. to a final sum.\n"
        "  (c) If it manually computes a product via partial products or shifts, collapse to\n"
        "      a single `assign p = a * b` and let the synthesizer optimize.\n"
        "  (d) If it has a multi-level mux built with bit-masking, simplify to a case\n"
        "      statement or nested ternary.\n"
        "  (e) Replace constant multiplications with shifts+adds (x*8 → x<<3, x*5 → (x<<2)+x).\n"
        "Choose whichever gives the largest gate-count reduction."
    ),

    # Strategy 1: Direct/clean rewrite — simple forms that synthesize well.
    (
        "Rewrite the module as directly and simply as possible:\n"
        "  - For a multiplier: `assign p = a * b;`\n"
        "  - For a 4:1 or N:1 mux: use a case statement on sel.\n"
        "  - For popcount: `always @(*) count = a[0]+a[1]+a[2]+a[3]+a[4]+a[5]+a[6]+a[7];`\n"
        "  - For a conditional arithmetic: use a single operator with muxed inputs.\n"
        "Remove any hand-coded loop, bit-mask, or partial-product structure — let the "
        "synthesizer produce the smallest netlist from a clean high-level description."
    ),

    # Strategy 2: Arithmetic operator sharing (original gen1 strategy 0).
    (
        "Share arithmetic operators under mutually-exclusive selects: replace "
        "two separate multipliers/adders used in an if-else or ternary with a "
        "single shared operator whose operands are muxed before the operation."
    ),

    # Strategy 3: Strength reduction and constant folding.
    (
        "Strength-reduce constant multiplies and divides to shifts and adds "
        "(e.g., x*8 -> x<<3, x*5 -> (x<<2)+x). Fold compile-time constants. "
        "Remove zero-padding and unnecessary width extensions."
    ),

    # Strategy 4: Mux/case simplification.
    (
        "Simplify and flatten cascaded case/if-else chains into a minimal "
        "equivalent combinational expression. For N:1 mux structures, "
        "use a clean case statement or nested ternaries with minimum logic."
    ),

    # Strategy 5: Dead code elimination and CSE.
    (
        "Identify and eliminate dead code; merge equivalent branches; "
        "apply common subexpression elimination. Look for signals that are "
        "computed but have the same value under all reachable conditions."
    ),

    # Strategy 6: Explicit adder tree for popcount/sum patterns.
    (
        "For population count or bit-sum: implement a Wallace-tree style reduction. "
        "Layer 1: add bit pairs to get 2-bit partial counts. "
        "Layer 2: add layer-1 outputs pairwise. Continue until one final sum. "
        "Each layer uses only addition of small signals — no loop, no integer."
    ),

    # Strategy 7: Interface-preserving logic minimization.
    (
        "Rewrite the module logic using the minimum number of operators. "
        "For boolean expressions, find the minimal sum-of-products. "
        "For arithmetic, look for algebraic simplifications like (a+b)-b == a. "
        "Merge any intermediate wire that is used only once."
    ),
]

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
SYSTEM_REWRITE = (
    "You are an expert hardware engineer specialising in RTL optimisation. "
    "You are given a CORRECT Verilog module. Rewrite it to use FEWER gates "
    "while preserving EXACT functional equivalence. "
    "Keep the module name, port names, port directions, and port widths IDENTICAL. "
    "Respond with exactly one Verilog module inside a single ```verilog code block — no prose."
)

SYSTEM_REFINE = (
    "You are an expert hardware engineer specialising in RTL optimisation. "
    "You are given a Verilog module that has ALREADY been partially optimized. "
    "Your goal is to reduce its gate count FURTHER while preserving EXACT functional "
    "equivalence. Look for any remaining redundancy or structural inefficiency. "
    "Keep the module name, port names, port directions, and port widths IDENTICAL to "
    "the ORIGINAL. "
    "Respond with exactly one Verilog module inside a single ```verilog code block — no prose."
)

SYSTEM_REPAIR = (
    "You are an expert hardware engineer. Your previous Verilog rewrite was rejected "
    "by the equivalence checker. Fix it so that it is EXACTLY equivalent to the "
    "original module while keeping it as small as possible. "
    "Keep the module name and interface IDENTICAL to the original. "
    "Respond with exactly one Verilog module inside a single ```verilog code block — no prose."
)


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------

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


def _log_user(trajectory_log: list, content: str) -> None:
    """Append a user message to the trajectory log."""
    trajectory_log.append({"role": "user", "content": [{"type": "text", "text": content}]})


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _rewrite_prompt(task, strategy: str) -> str:
    """Prompt for a fresh rewrite starting from the baseline."""
    return (
        f"Optimize the following Verilog module for gate count.\n"
        f"Strategy:\n{strategy}\n\n"
        f"```verilog\n{task.reference_rtl}\n```\n\n"
        f"Return the optimized module `{task.top_module}` with the SAME name and interface."
    )


def _refine_prompt(task, current_rtl: str, current_info: dict, strategy: str) -> str:
    """Prompt for further optimization of an already-improved candidate."""
    ref_cells = current_info.get("ref_cells", "?")
    cand_cells = current_info.get("cand_cells", "?")
    # Strip any markdown fences from the current best RTL to avoid double-wrapping.
    clean_rtl = extract_module(current_rtl, task.top_module) or current_rtl
    return (
        f"This module has been optimized from {ref_cells} to {cand_cells} cells. "
        f"Push it further — target fewer than {cand_cells} cells.\n\n"
        f"Additional strategy to try:\n{strategy}\n\n"
        f"Current optimized module ({cand_cells} cells):\n"
        f"```verilog\n{clean_rtl}\n```\n\n"
        f"Original interface to preserve (module name `{task.top_module}`, same ports):\n"
        f"```verilog\n{task.reference_rtl}\n```\n\n"
        f"Return a further-optimized version with FEWER than {cand_cells} cells, "
        f"preserving exact equivalence."
    )


def _repair_prompt(task, candidate: str, info: dict) -> str:
    """Prompt for repairing a failed candidate (compile error or equivalence failure)."""
    # Strip markdown from the candidate to show clean Verilog in the repair context.
    clean_cand = extract_module(candidate, task.top_module) or candidate
    if info.get("stage") == "compile_error":
        why = "it did not compile:\n" + info.get("log", "")[:800]
    else:
        p = info.get("eq_passed", 0)
        t = info.get("eq_total", 0)
        why = (
            f"it compiles but is NOT equivalent — "
            f"{t - p}/{t} output-vector comparisons mismatch."
        )
    return (
        f"Original (correct) module:\n\n```verilog\n{task.reference_rtl}\n```\n\n"
        f"Your rewrite was rejected: {why}\n\n"
        f"Your rejected rewrite:\n\n```verilog\n{clean_cand}\n```\n\n"
        f"Return a corrected, equivalent module with the SAME name and interface as the original."
    )


# ---------------------------------------------------------------------------
# Core optimization loop
# ---------------------------------------------------------------------------

def optimize_one(task, dataset_dir: str, working_dir: str) -> tuple:
    """Return (best_rtl, best_info, trajectory, candidate_log) for one design."""
    _log(
        "HARNESS",
        f"optimizing {task.task_id}: baseline + {N_CANDIDATES} rewrites "
        f"(temp={TEMPERATURE}, repair<={MAX_REPAIR_ROUNDS})",
    )

    trajectory: list[dict] = []
    trajectory.append({
        "role": "system",
        "content": [{"type": "text", "text": SYSTEM_REWRITE}],
    })

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

        # -----------------------------------------------------------------
        # Adaptive hill climbing:
        # If a previous candidate improved over baseline, build on it
        # (refinement). Otherwise, try a fresh strategy on the baseline.
        # -----------------------------------------------------------------
        if best_rtl is not task.reference_rtl:
            approach = f"refine{i}"
            _log(
                "HARNESS",
                f"{task.task_id}: refining best ({best_result.info.get('cand_cells')} cells) "
                f"round {i} — {strategy[:60]}...",
            )
            user_text = _refine_prompt(task, best_rtl, best_result.info, strategy)
            messages: list[dict] = [
                {"role": "system", "content": SYSTEM_REFINE},
                {"role": "user", "content": user_text},
            ]
        else:
            approach = f"rewrite{i}"
            _log(
                "HARNESS",
                f"{task.task_id}: sampling rewrite {i} — {strategy[:60]}...",
            )
            user_text = _rewrite_prompt(task, strategy)
            messages = [
                {"role": "system", "content": SYSTEM_REWRITE},
                {"role": "user", "content": user_text},
            ]

        _log_user(trajectory, user_text)
        cand = _chat(messages, trajectory)
        # Update messages with model reply for potential repair conversation
        messages.append({"role": "assistant", "content": cand})

        r = grade(cand, task, approach)
        rounds = 0

        # -----------------------------------------------------------------
        # Repair loop — GEN2 FIX: removed `r.info.get("compiled")` guard.
        # This means compile errors NOW receive repair attempts, not just
        # equivalence failures. Previously, popcount8's compile errors were
        # silently abandoned without any repair chance.
        # -----------------------------------------------------------------
        while rounds < MAX_REPAIR_ROUNDS and not r.info.get("equivalent"):
            rounds += 1
            stage = r.info.get("stage", "unknown")
            _log(
                "HARNESS",
                f"{task.task_id}: {approach} not equivalent "
                f"(stage={stage}) — repair {rounds}/{MAX_REPAIR_ROUNDS}",
            )
            # Use fresh messages for repair to avoid context contamination
            repair_text = _repair_prompt(task, cand, r.info)
            repair_messages = [
                {"role": "system", "content": SYSTEM_REPAIR},
                {"role": "user", "content": repair_text},
            ]
            _log_user(trajectory, repair_text)
            cand = _chat(repair_messages, trajectory)
            r = grade(cand, task, f"{approach}+repair{rounds}")

        entry = {
            "origin": approach,
            "reward": r.reward,
            "stage": r.info.get("stage"),
            "equivalent": bool(r.info.get("equivalent")),
            "area_improvement": r.info.get("area_improvement"),
        }
        candidate_log.append(entry)

        if r.reward > best_result.reward:
            best_result = r
            best_rtl = cand
            _log(
                "HARNESS",
                f"{task.task_id}: new best! cells={r.info.get('cand_cells')} "
                f"reward={r.reward:.3f}",
            )

    ai = best_result.info.get("area_improvement")
    ai_s = f"{ai * 100:+.1f}%" if ai is not None else "n/a"
    _log(
        "RESULT",
        f"{task.task_id}: best equiv={best_result.info.get('equivalent')} "
        f"area={ai_s} reward={best_result.reward:.3f}",
    )
    return best_rtl, best_result.info, trajectory, candidate_log


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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

        # Extract clean module text (strips markdown fences if present)
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

    # Save execution log
    (working_dir / "agent_execution.json").write_text(
        json.dumps(overall_trajectory, indent=2)
    )
    _log(
        "DONE",
        f"Processed {len(manifest['designs'])} design(s). "
        f"Outputs in {submission_dir}",
    )


if __name__ == "__main__":
    main()
