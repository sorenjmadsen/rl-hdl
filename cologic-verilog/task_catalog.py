"""Per-track TaskSpec catalog."""

from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
TASK_ROOT = ROOT_DIR / "tasks"


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    slug: str
    prompt: str
    track: str
    variant: str
    language: str
    module: str
    toolchain: str


STREAM_ARB_FIFO_REPAIR = TaskSpec(
    task_id="stream_arb_fifo_repair",
    slug="stream-arb-fifo-repair",
    prompt=(TASK_ROOT / "stream_arb_fifo_repair" / "prompt.md").read_text(
        encoding="utf-8"
    ),
    track="design",
    variant="repair_debug",
    language="systemverilog",
    module="stream_arb_fifo",
    toolchain="verilator+yosys",
)

STREAM_ARB_FIFO_COCOTB_DV = TaskSpec(
    task_id="stream_arb_fifo_cocotb_dv",
    slug="stream-arb-fifo-cocotb-dv",
    prompt=(TASK_ROOT / "stream_arb_fifo_cocotb_dv" / "prompt.md").read_text(
        encoding="utf-8"
    ),
    track="verification",
    variant="repair_debug",
    language="python+cocotb",
    module="stream_arb_fifo",
    toolchain="cocotb+verilator",
)

STREAM_ARB_FIFO_FORMAL = TaskSpec(
    task_id="stream_arb_fifo_formal",
    slug="stream-arb-fifo-formal",
    prompt=(TASK_ROOT / "stream_arb_fifo_formal" / "prompt.md").read_text(
        encoding="utf-8"
    ),
    track="formal",
    variant="repair_debug",
    language="systemverilog-formal",
    module="stream_arb_fifo",
    toolchain="symbiyosys+yosys",
)

TASK_SPECS = [
    STREAM_ARB_FIFO_REPAIR,
    STREAM_ARB_FIFO_COCOTB_DV,
    STREAM_ARB_FIFO_FORMAL,
]
TASK_SPECS_BY_ID = {spec.task_id: spec for spec in TASK_SPECS}
