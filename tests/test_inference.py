"""Inference config resolution + truncation auto-grow (no network / API key)."""

from cologic import inference
from cologic.schema import Port, Task

TASK = Task("t", "spec", "t", [Port("y", "output", 1)], "module t(output y); assign y=0; endmodule")


def test_max_tokens_defaults(monkeypatch):
    monkeypatch.delenv("RLHDL_MAX_TOKENS", raising=False)
    assert inference.max_tokens_setting() == inference.DEFAULT_MAX_TOKENS


def test_max_tokens_env_override(monkeypatch):
    monkeypatch.setenv("RLHDL_MAX_TOKENS", "8192")
    assert inference.max_tokens_setting() == 8192


def test_resolve_precedence(monkeypatch):
    monkeypatch.setenv("RLHDL_MAX_TOKENS", "2000")
    # override beats everything
    assert inference.resolve_max_tokens(TASK, override=999) == 999
    # Task.max_tokens beats env
    import dataclasses
    t = dataclasses.replace(TASK, max_tokens=3333)
    assert inference.resolve_max_tokens(t) == 3333
    # env beats default
    assert inference.resolve_max_tokens(TASK) == 2000


def test_sample_until_complete_grows_then_stops(monkeypatch):
    monkeypatch.delenv("RLHDL_MAX_TOKENS", raising=False)
    calls = []

    def fake(task, *, model=None, temperature=0.7, max_tokens=None):
        calls.append(max_tokens)
        # truncate until the budget reaches 16384, then succeed
        return ("ok", "stop" if max_tokens >= 16384 else "length")

    text, finish, budget = inference.sample_until_complete(TASK, max_tokens=4096, _complete=fake)
    assert finish == "stop" and budget == 16384
    assert calls == [4096, 8192, 16384]  # doubled each time


def test_sample_until_complete_caps_at_ceiling(monkeypatch):
    monkeypatch.delenv("RLHDL_MAX_TOKENS", raising=False)

    def always_truncate(task, *, model=None, temperature=0.7, max_tokens=None):
        return ("partial", "length")

    text, finish, budget = inference.sample_until_complete(
        TASK, max_tokens=8192, ceiling=16384, _complete=always_truncate
    )
    # stops growing at the ceiling even though still truncated
    assert finish == "length" and budget == 16384
