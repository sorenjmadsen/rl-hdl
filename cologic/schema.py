"""The locked seam: task schema + reward result type.

Both the verifier (CPU side) and the trainer (GPU side) build against the types
here. Keep changes to these signatures rare and deliberate.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Port:
    """A single port on the design-under-test.

    width is the bit width (1 for a scalar). direction is "input" or "output".
    """

    name: str
    direction: str
    width: int = 1

    def __post_init__(self) -> None:
        if self.direction not in ("input", "output"):
            raise ValueError(f"port {self.name}: direction must be input/output, got {self.direction!r}")
        if self.width < 1:
            raise ValueError(f"port {self.name}: width must be >= 1, got {self.width}")


@dataclass
class Task:
    """A (spec, interface, oracle) triple.

    The model sees `spec` (and is told the required module name + interface). The
    oracle is `reference_rtl`: a known-correct Verilog module named `top_module`.
    Grading drives random input vectors into both the candidate and the reference
    and rewards the fraction of output comparisons that match — so the reward is
    dense and we never hand-author expected values.

    `held_out=True` marks tasks reserved for the headline metric / reward-hacking
    gap check; they should be perturbed away from any public benchmark.
    """

    task_id: str
    spec: str
    top_module: str
    interface: list[Port]
    reference_rtl: str
    n_vectors: int = 64
    seed: int = 1
    held_out: bool = False
    # Most v1 tasks are combinational. Clocked tasks use a task-specific
    # self-checking testbench while preserving the public grade() seam.
    clocked: bool = False
    testbench_template: str | None = None
    allow_extra_modules: bool = False
    tags: list[str] = field(default_factory=list)
    # Per-task generation budget (overrides the global default); larger designs
    # need more room. None -> fall back to the global RLHDL_MAX_TOKENS / default.
    max_tokens: int | None = None
    # When the spec already contains the full prompt + interface (e.g. ingested
    # benchmark problems), use it verbatim instead of appending our interface block.
    prompt_is_complete: bool = False

    @property
    def inputs(self) -> list[Port]:
        return [p for p in self.interface if p.direction == "input"]

    @property
    def outputs(self) -> list[Port]:
        return [p for p in self.interface if p.direction == "output"]

    def interface_str(self) -> str:
        """Human-readable interface block to embed in the prompt."""
        lines = [f"module {self.top_module} ("]
        decls = []
        for p in self.interface:
            w = "" if p.width == 1 else f"[{p.width - 1}:0] "
            decls.append(f"    {p.direction} {w}{p.name}")
        lines.append(",\n".join(decls))
        lines.append(");")
        return "\n".join(lines)


@dataclass
class GradeResult:
    """Return type of grade(). reward is in [0, 1]; info carries diagnostics.

    info keys (stable contract for observability / logging):
      stage        : "no_module" | "compile_error" | "sim_error" | "graded"
      compiled     : bool
      passed       : int   (output comparisons that matched)
      total        : int   (output comparisons run)
      log          : str   (tool stderr/stdout, truncated)
    """

    reward: float
    info: dict
