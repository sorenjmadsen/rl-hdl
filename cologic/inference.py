"""Policy-model inference via Fireworks (OpenAI-compatible API).

Used for the zero-shot baseline and, later, for RL rollouts. Provider-agnostic:
point FIREWORKS_BASE_URL / FIREWORKS_API_KEY elsewhere (e.g. a local vLLM
server) and nothing else changes.

Env:
  FIREWORKS_API_KEY   (required)
  FIREWORKS_BASE_URL  (default https://api.fireworks.ai/inference/v1)
  RLHDL_MODEL         (default a Qwen-Coder 7B; the warm-start policy)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from cologic.prompt import build_messages
from cologic.schema import Task

DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"
# Verilog-capable warm-start. Override via RLHDL_MODEL once the exact Fireworks
# model id / a fine-tune is confirmed.
DEFAULT_MODEL = "accounts/fireworks/models/qwen2p5-coder-7b-instruct"


def _client():
    try:
        from openai import OpenAI
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install openai (or rl-hdl[eval]) to use inference.") from e
    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        raise RuntimeError("set FIREWORKS_API_KEY to sample completions.")
    return OpenAI(api_key=api_key, base_url=os.environ.get("FIREWORKS_BASE_URL", DEFAULT_BASE_URL))


def model_id() -> str:
    return os.environ.get("RLHDL_MODEL", DEFAULT_MODEL)


def complete(
    task: Task,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    top_p: float = 0.95,
    max_tokens: int = 1024,
) -> str:
    """One completion for one task."""
    resp = _client().chat.completions.create(
        model=model or model_id(),
        messages=build_messages(task),
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def sample(tasks: list[Task], n: int, *, max_workers: int = 16, **kw) -> list[tuple[Task, str]]:
    """Sample `n` completions for each task, concurrently.

    Returns a flat list of (task, completion) pairs ready to hand to a grader's
    parallel map. Greedy (n==1) lowers temperature for a stable baseline read.
    """
    if n == 1:
        kw.setdefault("temperature", 0.0)
    jobs = [t for t in tasks for _ in range(n)]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        completions = list(pool.map(lambda t: complete(t, **kw), jobs))
    return list(zip(jobs, completions))
