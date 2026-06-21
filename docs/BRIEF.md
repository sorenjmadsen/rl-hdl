# RSI Hackathon — Build Brief: An RL Environment for Verilog/RTL Generation

> This is the original planning brief for the project, preserved verbatim as the
> source of record for scope and decisions. Implementation notes live in the
> top-level [README](../README.md).

**You are leading setup, coding, integration, and the final presentation for a 24-hour, 2-person hackathon project at the HUD × YC RSI Hackathon.** The hackathon thesis: *you can improve models at anything you can verify — the only question is what you teach them.* Build accordingly.

> Note: verify every repo/paper URL with a quick web search before relying on it — links reflect best knowledge as of the planning session, and the RTL-LLM field moves weekly.

---

## 1. The idea (one line)

An RL-with-verifiable-rewards (RLVR) **environment** that teaches an LLM to generate correct hardware (Verilog/RTL) from a spec, where the reward comes from **real silicon tooling — a simulator and synthesizer — not an LLM judge**. The model gets a grade that physically cannot be faked.

## 2. Why this framing (decisions locked — do not relitigate)

- **The LLM is genuinely the unlock here.** Writing correct, efficient RTL from a spec is open-ended program synthesis over a huge prior; a from-scratch policy net can't do it, and frontier models are documented-mediocre at it (headroom exists). Keep the task in the *design-from-spec* regime — never let it collapse into numeric knob-tuning (that's classic autotuning, where the LLM adds nothing).
- **The verifier is a mechanism, not a judgment.** Verilator (simulation) and Yosys (synthesis) are non-lying oracles: hardware computes the right function or it doesn't. This dissolves the reward-trust/regress problem entirely — no LLM judge anywhere in the reward path.
- **Vanilla RLVR-for-Verilog is already published and saturated** (VeriReason, CodeV-R1, ChipSeek, EARL — see §4). So this is **not** a SOTA claim. The strength is (a) a clean working environment + the verification-magic demo, and (b) the differentiator below.
- **Differentiator = the SIA dual-lever, applied to hardware.** All existing RTL work is weights-only. None co-evolves the *harness* (the scaffold/feedback the generator works inside) alongside the weights. SIA demonstrated dual-lever on the TriMul CUDA-kernel task — structurally a sibling of RTL gen (low-level code, mechanical oracle, correctness+performance). Bringing it to RTL is novel. **Floor first, then SIA-ify.**

## 3. Stack & tools

- **Environment platform:** HUD — https://hud.ai (RL environments + agentic evals)
- **Compute / sandboxes:** Modal — https://modal.com (GPU for training/rollouts; parallel CPU sandboxes for grading)
- **Fine-tuning (open models):** Fireworks — https://fireworks.ai (optional path; or train on Modal directly)
- **Verifier (correctness):** Verilator — https://github.com/verilator/verilator
- **Verifier (PPA, optional/demo):** Yosys — https://github.com/YosysHQ/yosys
- **RL trainer (do NOT hand-roll):** TRL GRPOTrainer — https://github.com/huggingface/trl · verifiers — https://github.com/willccbb/verifiers · prime-rl — https://github.com/PrimeIntellect-ai/prime-rl
- **Inference for rollouts:** vLLM
- **Policy model (warm-start):** CodeV or RTLCoder (Verilog-specialized, Qwen-Coder-based) — confirm current repos/HF cards
- **Baseline / harness brain:** Claude (Anthropic) as the zero-shot baseline-to-beat and, for the stretch, the SIA Feedback-Agent
- **Tasks/benchmarks:** VerilogEval (NVIDIA), RTLLM — ship (spec, interface, hidden testbench) triples; confirm repos

## 4. Prior art (and how we differ)

- **SIA: Self-Improving AI with Harness & Weight Updates** — https://arxiv.org/abs/2605.27276 — the dual-lever method we extend. Key finding: harness updates = SWE plumbing; weight updates = domain knowledge; verifier must stay grounded; coupled co-evolution can Goodhart even a grounded verifier (→ use held-out checks).
- **VeriReason** — https://arxiv.org/abs/2505.11849 — SFT + GRPO + testbench reward + self-correction (~83% VerilogEval-Machine). *This is essentially the vanilla floor; we are not claiming novelty over it.*
- **CodeV-R1 / QiMeng** — https://qimeng-ict.github.io — RLVR + rule-based testbench gen + distill-then-RL; beats 671B DeepSeek-R1 on RTLLM. *Do not try to beat its numbers in 24h.*
- **ChipSeek** — https://arxiv.org/abs/2507.04736 — EDA-integrated RL; shows vanilla GRPO/DAPO underperform on multi-objective correctness+PPA (they built CDPO). **Implication: keep PPA out of the RL objective for v1.**
- **EARL** — https://arxiv.org/abs/2511.12033 — entropy-aware RLVR for RTL.
- **awesome-RLVR** — https://github.com/opendilab/awesome-RLVR — landscape index.

## 5. System architecture (the loop)

```
Task store (VerilogEval/RTLLM: spec + interface + hidden testbench; + held-out/randomized testbenches)
   │
   ▼
Policy model (warm-start CodeV/RTLCoder, served via vLLM)  ──►  sample N completions/task (SINGLE-SHOT v1)
   │
   ▼
Grading (Modal CPU sandboxes, parallel): Verilator simulate → dense reward = % vectors passing
   (Yosys synth ONLY if correct → area/timing; v1: skip or demo-only)
   │
   ▼
Reward = correctness-dominant (PPA at most a light tiebreak among passers)
   │
   ▼
Trainer: GRPO (group-relative, LoRA + KL to reference) via TRL/verifiers/prime-rl  ──► update weights ──► back to policy
   │
   ▼
Eval / Observability: pass@1 on held-out, train-vs-heldout gap (hack check), reward + throughput curves
```

The only exotic part is the grader. Everything else is imported.

## 6. Build plan & critical path (de-risked)

**Reframe: you will not get the big RL run right on the first try — nobody does. Make the loop cheap and instrumented so you converge on a working config in hours.**

1. **Verifier** returning a dense reward on ONE hardcoded design (Verilator only). *(foundation)*
2. **Env wrapper** + task curation (5–15 tasks + held-out).
3. **Baseline eval** (zero-shot pass@1 on held-out). ← **FLOOR: a complete, demoable submission even if nothing else lands.**
4. **Smallest RL loop**: small/warm-started model, ~5–10 tasks, single-shot, GRPO via library — run until **reward visibly moves on the toy**. ← the milestone that de-risks everything. Hit it **Saturday evening, not Sunday morning.**
5. Scale tasks/model; tune reward shaping.
6. **Stretch (Sun AM only):** SIA harness lever (Feedback-Agent iterates compile-error/failing-vector/synth-warning feedback + retrieved patterns; show harness+weights > weights-only). Then PPA-in-demo, agentic revise loop.

## 7. Division of labor (2 people)

**Lock the reward interface in the first 30 minutes:** `grade(completion, task) -> (reward: float, info: dict)` + the task schema. Then both build against stubs and meet at that seam. Integrate by hour ~8–10.

- **Person A — Environment & Verifier (CPU side, the floor).** Verilator-in-sandbox, task curation + held-out split, robust Verilog extraction, the dense reward function, eval harness, demo visuals. Testable immediately on hand-written good/bad Verilog; no GPU. Output is a complete submission on its own.
- **Person B — Training & Infra (GPU side, the risk).** Modal (GPU train + parallel CPU grading sandboxes), model + vLLM rollouts, GRPO loop wired to A's reward, throughput, checkpoints, curves. Develops against a stub reward until A's lands.

**Recommended:** Soren → Person B (RL+Modal strength; doubles as Modal-interview reps; strongest person on the risk path). Teammate → Person A (the floor). Swap only if the teammate is the RL/infra one.

## 8. RL de-risking checklist

- **Dead signal is the #1 killer.** Prevent with all three: warm-start (non-zero baseline pass-rate), *dense* reward (% vectors + partial credit for compiling — never bare pass/fail), and difficulty calibrated so the warm-started model sits ~20–60%. Reward must vary *within* the GRPO group.
- **Throughput:** parallelize grading hard across Modal sandboxes; gate Yosys behind correctness; measure rollouts/sec on day one.
- **Keep it single-shot** for v1 (revise loop triples rollout length and muddies credit assignment).
- **Stability:** LoRA + KL to warm-start reference + conservative LR. Keep **rejection-sampling-SFT** (sample N, keep passers, SFT) as the can't-fail fallback.
- **Observability before training:** stand up eval + live curves first; you must see movement within minutes or you're blind.
- **Reward-hacking guard:** hold out a randomized testbench; watch the train-pass vs held-out-pass gap (also a great "here's how it tried to cheat, here's how we caught it" slide).
- **Eval credibility:** VerilogEval/RTLLM are public and warm-start models may have trained on them — use novel/perturbed tasks (rename signals, change widths, recombine) for the headline number, or the gain is illusory.

## 9. Scope: in / out

- **IN (must-have):** Verilator verifier + dense reward; 5–15 tasks + held-out; thin HUD env; warm-started 7B + GRPO via library on Modal; baseline eval + curves.
- **OUT (stretch only):** Yosys/PPA in the objective; agentic revise loop; SIA harness lever; full meta-agent + dynamic algorithm selection; large task set/model.

## 10. The presentation (≈3 min, not too technical)

**The magic is the proof:** every other AI demo asks the room to trust the output; this is the one they don't have to, because the physics already checked.

1. **Hook (15s):** "Every AI demo you've watched, you had to trust. Ours, you won't — and that's the point."
2. **Insight (20s):** the hackathon's rule is "teach a model anything you can verify"; almost nothing truly is — except hardware, where a circuit works or it doesn't, instantly.
3. **Magic moment (60s):** one legible spec, live. Base model swings and fails (red). Trained model succeeds (green). "It works — and don't take my word for it, that's the simulator. The physics already checked." (The fail→succeed contrast IS the magic.)
4. **Result (30s):** pass@1 cold vs after training, on held-out; one curve climbing. (Frame as environment + loop, not new SOTA.)
5. **Landing (15s):** "The chips these models run on are designed by people today. We showed they can be designed by the models — and proven correct, nobody in the loop. That's the only self-improvement loop that can't lie to itself. That's the road to 2040."

**Optional upgrades:** take a spec from the audience (un-cherry-pickable); if the trained model ever beats the textbook design on gate count, lead with it (the AlphaChip beat). **Pre-record the live demo as backup; present it as live.**

## 11. Definition of done

- **Floor (must):** working HUD env + Verilator-grounded dense reward + baseline pass@1 on held-out + the verification-magic demo.
- **Win (target):** RFT visibly moves held-out pass@1 above the zero-shot baseline, shown live.
- **Stretch (bonus):** SIA harness lever beats weights-only; PPA/"fewer gates" demo beat.
