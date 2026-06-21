# SIA harness-lever run 12

meta=sonnet · target=accounts/fireworks/models/kimi-k2p7-code · max_gen=2 · n_candidates=2

Footprint per generation (official score from evaluate.py = deployed verifier):

| generation | mean_reward | mean_area_improvement | equivalent |
|---|---|---|---|
| gen_1 | 0.6404 | +28.1% | 4/4 |
| gen_2 | 0.6404 | +28.1% | 4/4 |

Artifacts: per-generation `target_agent.py` (the evolved harness), `results.json`, `agent_execution.json`, `context.md`, and `target_agent_gen1_to_gen2.diff`.
