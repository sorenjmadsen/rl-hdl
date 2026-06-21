"""Prompt construction: turn a Task into the messages we send the policy model.

Kept deliberately plain — the same prompt format is used for the zero-shot
baseline and for RL rollouts, so the baseline number is honest.
"""

from __future__ import annotations

from cologic.schema import Task

SYSTEM = (
    "You are an expert hardware engineer. You write correct, synthesizable Verilog. "
    "Respond with exactly one Verilog module and nothing else: no explanation, no "
    "testbench, no prose. Put the module in a single ```verilog code block."
)


def build_user_prompt(task: Task) -> str:
    return (
        f"{task.spec}\n\n"
        f"Write a Verilog module named `{task.top_module}` with exactly this interface:\n\n"
        f"```verilog\n{task.interface_str()}\n```\n\n"
        f"Use these exact port names, directions, and widths."
    )


def build_messages(task: Task) -> list[dict]:
    """OpenAI/Fireworks-style chat messages for a task."""
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": build_user_prompt(task)},
    ]
