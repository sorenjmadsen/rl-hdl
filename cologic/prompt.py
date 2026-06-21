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
    # Ingested benchmark prompts already state the module name + interface.
    if task.prompt_is_complete:
        return task.spec
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


SYSTEM_OPTIMIZE = (
    "You are an expert hardware engineer. You are given a CORRECT Verilog module and must "
    "rewrite it to use FEWER gates while preserving EXACT functional equivalence. Keep the "
    "module name, port names, directions, and widths identical. Respond with exactly one "
    "Verilog module in a single ```verilog code block — no explanation, no testbench, no prose."
)


def build_optimize_messages(task: Task) -> list[dict]:
    """Chat messages for the OPTIMIZATION objective: rewrite `task.reference_rtl`
    (a correct baseline) into a smaller, equivalent module with the same interface.

    Used by the RFT weight lever so the policy is trained to optimize, not generate.
    The reward still comes only from the immutable grader (equivalence + Yosys PPA).
    """
    return [
        {"role": "system", "content": SYSTEM_OPTIMIZE},
        {"role": "user", "content": (
            f"Optimize this module for gate count while keeping it exactly equivalent.\n\n"
            f"```verilog\n{task.reference_rtl}\n```\n\n"
            f"Return the optimized module `{task.top_module}` with the same name and interface."
        )},
    ]
