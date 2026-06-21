"""The three-agent self-improvement loop on top of the cologic reward seam.

Plan (Claude) -> Forge (policy model writes RTL) -> Prove (Verilator grades it)
-> feedback -> repeat, keeping the best design until it stops improving.

See agents/README.md for the design and the backend APIs this needs.
"""

from agents.loop import Forge, Plan, Prove, Attempt, improve, feedback_from

__all__ = ["Plan", "Forge", "Prove", "Attempt", "improve", "feedback_from"]
