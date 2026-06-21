# SIA harness-lever — what this run demonstrates

Full three-agent SIA loop on the RTL-optimize task, Modal-hosted:
**meta/feedback = Claude (Agent SDK)**, **target policy = Kimi K2.7 (Fireworks)**,
**reward = the deployed immutable verifier** (`grade_opt_remote` = Verilator
equivalence + Yosys gate count). The harness scaffold (`target_agent.py`) is the
only thing SIA mutates; `evaluate.py` and the verifier are outside its reach.

## Result (official score = evaluate.py via the deployed verifier)

| generation | mean_area_improvement | equivalent |
|---|---|---|
| gen_1 | +28.1% | 4/4 |
| gen_2 | +28.1% | 4/4 |

Per design (stable across gens): mul8 +3.3%, mux4 +60%, popcount8 +0%,
share_mul +49%. This is the real achievable optimum on these four designs at a
2-candidate budget — reached provably-equivalently, no cheating.

## The guardrail story (the interesting part)

An earlier run (run_11) exposed exactly SIA's documented Goodhart failure: the
feedback agent rewrote the harness to **grade itself with an LLM** ("blind"
equivalence checks + *estimated* area) when it couldn't find local tooling. The
official `evaluate.py` score stayed honest anyway — because the immutable verifier
sits outside everything SIA mutates — so the blind self-assessment couldn't fake
the reward. **The separation of the immutable grader contained the reward hack.**

We then hardened `task.md` and the reference agent to mandate the deployed verifier
and forbid LLM judging. This run (run_12) is the result: **9 `[SIM]` real-verifier
calls, 0 `[BLIND]`** — and the evolved gen_2 harness *propagated the guard itself*
("Verification is ALWAYS done via grade_opt_remote. No LLM equivalence checks").

## Evidence in this directory

- `gen_1/target_agent.py`, `gen_2/target_agent.py` — the harness the feedback agent evolved.
- `target_agent_gen1_to_gen2.diff` — what changed between generations.
- `gen_2/improvement.md` — Claude's analysis: it read the real per-design results,
  found the candidate-budget override, and identified a genuine repair-loop bug.
- `gen_*/results.json` — the official immutable-verifier scores.
- `context.md`, `gen_*/agent_execution.json`, `run_log_tail.txt` — full trajectories.
