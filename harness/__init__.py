"""harness/ — the MAGE-repurposed RTL optimizer (the SIA target agent).

This is the harness lever's scaffold: SIA's Feedback-Agent evolves `optimizer.py`
across generations. It optimizes a correct design for PPA, graded only by the
immutable grader (cologic.grader). See optimizer.py for the guardrails.
"""

from __future__ import annotations

from harness.flywheel import FlywheelConfig, FlywheelResult, Generation, run_flywheel
from harness.measure import (
    ZERO_SHOT_CONFIG,
    Arm,
    GapResult,
    format_gap,
    measure_gap,
)
from harness.optimizer import (
    Candidate,
    HarnessConfig,
    OptimizeResult,
    default_model_fn,
    optimize,
)

__all__ = [
    "optimize",
    "HarnessConfig",
    "OptimizeResult",
    "Candidate",
    "default_model_fn",
    "run_flywheel",
    "FlywheelConfig",
    "FlywheelResult",
    "Generation",
    "measure_gap",
    "format_gap",
    "GapResult",
    "Arm",
    "ZERO_SHOT_CONFIG",
]
