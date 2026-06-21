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
    # Tolerate transient 429/5xx (e.g. a deployment scaling up from zero) so one
    # hiccup doesn't crash a whole sampling map. OpenAI client backs off exponentially.
    return OpenAI(
        api_key=api_key,
        base_url=os.environ.get("FIREWORKS_BASE_URL", DEFAULT_BASE_URL),
        max_retries=6,
    )


def model_id() -> str:
    return os.environ.get("RLHDL_MODEL", DEFAULT_MODEL)


# Headroom for models that emit reasoning before the module: at 1024, harder
# tasks get truncated mid-module (finish_reason="length") and extract to nothing.
# Override with RLHDL_MAX_TOKENS (e.g. 8192) to chase reasoning-heavy worst cases.
DEFAULT_MAX_TOKENS = 4096
# Auto-grow ceiling: how high sample_until_complete will push the budget before
# giving up on a still-truncating completion. Override with RLHDL_MAX_TOKENS_CEILING.
DEFAULT_MAX_TOKENS_CEILING = 16384


def max_tokens_setting() -> int:
    return int(os.environ.get("RLHDL_MAX_TOKENS", DEFAULT_MAX_TOKENS))


def max_tokens_ceiling() -> int:
    return int(os.environ.get("RLHDL_MAX_TOKENS_CEILING", DEFAULT_MAX_TOKENS_CEILING))


def resolve_max_tokens(task: Task, override: int | None = None) -> int:
    """Budget precedence: explicit override (e.g. --max-tokens) > Task.max_tokens
    > RLHDL_MAX_TOKENS env > DEFAULT_MAX_TOKENS."""
    if override is not None:
        return override
    if task.max_tokens is not None:
        return task.max_tokens
    return max_tokens_setting()


def sample_until_complete(
    task: Task,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    ceiling: int | None = None,
    _complete=None,
) -> tuple[str, str, int]:
    """Sample, doubling the budget while the output is truncated.

    A `finish_reason == "length"` is a token-budget artifact, never a task signal
    (efficiency must come from hardware, not output length), so we grow the budget
    (2x, up to `ceiling`) and resample rather than scoring the truncation. Returns
    (text, finish_reason, budget_used). `_complete` is injectable for tests.
    """
    complete_fn = _complete or complete_raw
    budget = resolve_max_tokens(task, max_tokens)
    cap = ceiling if ceiling is not None else max_tokens_ceiling()
    while True:
        text, finish = complete_fn(task, model=model, temperature=temperature, max_tokens=budget)
        if finish != "length" or budget >= cap:
            return text, finish, budget
        budget = min(budget * 2, cap)


def complete_raw(
    task: Task,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    top_p: float = 0.95,
    max_tokens: int | None = None,
) -> tuple[str, str]:
    """One completion; returns (text, finish_reason).

    finish_reason == "length" means the model hit the token cap mid-output — the
    usual cause of a missing `endmodule` and a 0.0 (no_module) grade.
    """
    resp = _client().chat.completions.create(
        model=model or model_id(),
        messages=build_messages(task),
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens if max_tokens is not None else max_tokens_setting(),
    )
    choice = resp.choices[0]
    return choice.message.content or "", (choice.finish_reason or "?")


def complete(task: Task, **kw) -> str:
    """One completion (text only)."""
    return complete_raw(task, **kw)[0]


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
