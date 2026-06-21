"""MAGE repurposed as an RTL optimizer — the SIA target agent.

This is the harness lever's starting scaffold: the file SIA's Feedback-Agent
rewrites across generations (knobs, prompts, sampling schedule, debug budget).
Per build brief §5 we keep MAGE's machinery and swap the objective from
generation to optimization:

  high-temp multi-candidate sampling  ->  structural-rewrite diversity engine
  judge + Verilog-state checkpoint     ->  equivalence gate (immutable grader)
  debug agent                          ->  repair loop when a rewrite breaks equiv
  (ADD) Yosys PPA scorer               ->  rank equivalent survivors by gate count

GUARDRAILS (locked, brief §8):
  1. Reward comes ONLY from the immutable grader (cologic.grader.grade =
     Verilator equivalence + Yosys PPA). The scaffold may use an LLM to *steer*
     (which candidate to repair, which strategy to try) but NEVER to score.
  2. This harness is what SIA evolves and what we put on stage. It is NOT nested
     inside ES population evals — that lever runs the bare policy + grade().

Action space = structural rewrites only (brief §8), never numeric knob sweeps.

The model is an injected callable (messages -> text), so the whole loop runs
offline in tests with a stub. `default_model_fn` wires the real Fireworks policy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from cologic.grader import grade as default_grade
from cologic.schema import GradeResult, Task

# A model is: (messages, *, temperature, max_tokens) -> completion text.
ModelFn = Callable[..., str]
# A grader is: (candidate_rtl, task) -> GradeResult. Defaults to the immutable grader.
GraderFn = Callable[[str, Task], GradeResult]

# The structural-rewrite menu. These are the *moves* the policy is asked to make;
# SIA may add/remove/reword them. Never numeric parameter sweeps (that's autotuning).
DEFAULT_STRATEGIES: tuple[str, ...] = (
    "Share arithmetic resources: reuse one adder/multiplier across paths instead of instantiating many.",
    "Strength-reduce: replace multiplies/divides by constants with shifts and adds.",
    "Eliminate redundant, duplicated, or dead logic; fold constants.",
    "Re-encode the FSM or flatten/simplify case and if-else chains.",
    "Rebalance the datapath into a more compact but equivalent structure.",
    "Re-pipeline / rebalance the critical path without changing the function.",
)

SYSTEM_REWRITE = (
    "You are an expert hardware engineer. You are given a CORRECT Verilog module and must "
    "rewrite it to use FEWER gates while preserving EXACT functional equivalence. Keep the "
    "module name, port names, directions, and widths identical. Respond with exactly one "
    "Verilog module in a single ```verilog code block — no prose, no testbench."
)

SYSTEM_REPAIR = (
    "You are an expert hardware engineer. Your previous rewrite of a Verilog module was "
    "rejected by the equivalence checker. Fix it so it is exactly equivalent to the original "
    "while staying as small as you can. Keep the module name and interface identical. Respond "
    "with exactly one Verilog module in a single ```verilog code block — no prose."
)


def build_rewrite_messages(task: Task, strategy: str) -> list[dict]:
    """Front-end: ask the policy for one structural rewrite of the baseline."""
    return [
        {"role": "system", "content": SYSTEM_REWRITE},
        {"role": "user", "content": (
            f"Optimize this module for gate count. Apply this strategy where it helps:\n"
            f"  {strategy}\n\n"
            f"Original (already correct) module `{task.top_module}`:\n\n"
            f"```verilog\n{task.reference_rtl}\n```\n\n"
            f"Return the optimized module with the same name and interface."
        )},
    ]


def build_repair_messages(task: Task, candidate: str, info: dict) -> list[dict]:
    """Debug agent: feed the grader's verdict back so the model fixes the break."""
    return [
        {"role": "system", "content": SYSTEM_REPAIR},
        {"role": "user", "content": (
            f"Original (correct) module `{task.top_module}`:\n\n"
            f"```verilog\n{task.reference_rtl}\n```\n\n"
            f"Your rewrite was rejected: {_repair_hint(info)}\n\n"
            f"Your rejected rewrite:\n\n```verilog\n{candidate}\n```\n\n"
            f"Return a corrected, equivalent module with the same name and interface."
        )},
    ]


def _repair_hint(info: dict) -> str:
    """Turn the immutable grader's info into a one-line, actionable critique.

    Reads only the stable info contract from cologic.grader — never recomputes reward.
    """
    stage = info.get("stage")
    if stage == "compile_error":
        return "it did not compile:\n" + (info.get("log", "")[:800])
    if stage == "sim_error":
        return "it compiled but the simulation failed to run:\n" + (info.get("log", "")[:800])
    p, t = info.get("eq_passed", 0), info.get("eq_total", 0)
    return (f"it compiles but is NOT equivalent — {t - p}/{t} output-vector comparisons "
            f"mismatch the original. The logic is wrong on some inputs.")


@dataclass
class HarnessConfig:
    """The harness search space — the knobs SIA's Feedback-Agent tunes across gens."""

    n_candidates: int = 8          # high-temp rewrite samples per design
    temperature: float = 0.9       # diversity engine temperature
    max_repair_rounds: int = 2     # debug-agent budget per broken candidate
    keep_baseline: bool = True     # seed the pool with the reference (reward floor)
    max_tokens: int = 4096
    strategies: tuple[str, ...] = DEFAULT_STRATEGIES


@dataclass
class Candidate:
    origin: str        # "baseline" | "rewrite[<strategy>]" | "<...>+repair"
    rtl: str
    reward: float
    info: dict

    @property
    def equivalent(self) -> bool:
        return bool(self.info.get("equivalent"))


@dataclass
class OptimizeResult:
    best: Candidate
    pool: list[Candidate] = field(default_factory=list)

    @property
    def baseline_reward(self) -> float:
        base = next((c for c in self.pool if c.origin == "baseline"), None)
        return base.reward if base else 0.0

    @property
    def n_equivalent(self) -> int:
        return sum(c.equivalent for c in self.pool)

    @property
    def improved(self) -> bool:
        """Did we find an equivalent design that beats the baseline's reward?"""
        return self.best.equivalent and self.best.reward > self.baseline_reward


def optimize(
    task: Task,
    *,
    model_fn: ModelFn,
    grader: GraderFn | None = None,
    config: HarnessConfig | None = None,
) -> OptimizeResult:
    """Run the MAGE-repurposed optimizer on one design and return the best survivor.

    Pipeline: seed baseline -> sample N structural rewrites (high temp, round-robin
    over strategies) -> grade each through the immutable gate -> repair the ones
    that compiled but broke equivalence -> return the highest-reward candidate
    (equivalence + PPA, both from the grader).
    """
    cfg = config or HarnessConfig()
    grade = grader or default_grade
    rng = random.Random(task.seed)

    def grade_candidate(rtl: str, origin: str) -> Candidate:
        r = grade(rtl, task)
        return Candidate(origin, rtl, r.reward, r.info)

    pool: list[Candidate] = []
    if cfg.keep_baseline:
        pool.append(grade_candidate(task.reference_rtl, "baseline"))

    # Diversity engine: round-robin the strategy menu, shuffled so SIA's ordering
    # isn't load-bearing.
    order = list(range(cfg.n_candidates))
    rng.shuffle(order)
    for k, i in enumerate(order):
        strategy = cfg.strategies[i % len(cfg.strategies)]
        rtl = model_fn(
            build_rewrite_messages(task, strategy),
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        pool.append(grade_candidate(rtl, f"rewrite[{strategy[:24]}...]"))

    # Debug agent: repair candidates that compiled but broke equivalence. (A
    # candidate that won't even compile is usually not worth the repair budget.)
    for cand in list(pool):
        cur = cand
        rounds = 0
        while (rounds < cfg.max_repair_rounds
               and cur.info.get("compiled") and not cur.equivalent):
            rtl = model_fn(
                build_repair_messages(task, cur.rtl, cur.info),
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
            cur = grade_candidate(rtl, f"{cand.origin}+repair{rounds + 1}")
            pool.append(cur)
            rounds += 1

    best = max(pool, key=lambda c: c.reward)
    return OptimizeResult(best=best, pool=pool)


def default_model_fn(messages: list[dict], *, temperature: float = 0.9,
                     max_tokens: int = 4096, model: str | None = None) -> str:
    """Real policy: the warm-start Verilog model on Fireworks (needs FIREWORKS_API_KEY)."""
    from cologic.inference import _client, model_id

    resp = _client().chat.completions.create(
        model=model or model_id(),
        messages=messages,
        temperature=temperature,
        top_p=0.95,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def demo() -> None:
    """Offline control-flow check — no API key, no Verilator (stub model + grader).

    A broken first rewrite is repaired into a smaller equivalent design; the loop
    returns it as the best, beating the baseline."""
    from cologic.schema import Port

    task = Task(
        task_id="t", spec="x", top_module="m",
        interface=[Port("a", "input"), Port("b", "input"), Port("y", "output")],
        reference_rtl="module m(input a, input b, output y); assign y = a & b; endmodule",
    )

    def stub_model(messages, *, temperature, max_tokens):
        is_repair = any("rejected" in m["content"].lower() for m in messages)
        if is_repair:
            return "module m(input a, input b, output y); assign y = b & a; endmodule"  # equiv, "smaller"
        return "module m(input a, input b, output y); assign y = a | b; endmodule"  # WRONG

    def stub_grader(rtl: str, _task: Task) -> GradeResult:
        if "a & b" in rtl or "b & a" in rtl:
            cells = 1 if "b & a" in rtl else 2  # the rewrite is "smaller"
            ref = 2
            improvement = (ref - cells) / ref
            return GradeResult(0.5 + 0.5 * improvement, {
                "stage": "graded", "compiled": True, "equivalent": True,
                "eq_passed": 4, "eq_total": 4, "ref_cells": ref, "cand_cells": cells,
                "area_improvement": improvement,
            })
        return GradeResult(0.10, {"stage": "not_equivalent", "compiled": True,
                                  "equivalent": False, "eq_passed": 3, "eq_total": 4})

    res = optimize(task, model_fn=stub_model, grader=stub_grader,
                   config=HarnessConfig(n_candidates=3, max_repair_rounds=1))
    assert res.best.equivalent, res.best
    assert res.improved, (res.best.reward, res.baseline_reward)
    assert any(not c.equivalent for c in res.pool), "expected a rejected candidate in the pool"
    assert any("repair" in c.origin for c in res.pool), "expected a repair attempt"
    print(f"demo ok: {len(res.pool)} candidates, {res.n_equivalent} equivalent, "
          f"best reward {res.best.reward:.3f} (baseline {res.baseline_reward:.3f}) via {res.best.origin}")


if __name__ == "__main__":
    demo()
