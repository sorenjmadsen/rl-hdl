"""Per-task workspace setup for the built image and LocalRuntime.

Image: agent works in ``/workdir``, hidden key at ``/donotaccess/<id>`` (root:700). Local
subprocess: a per-process scratch dir under the temp dir, hidden dir ``tasks/<id>/donotaccess``.
``setup_task`` rebuilds the workspace from the agent-facing baseline each episode (never
copying ``donotaccess`` in), with an optional golden_pass overlay.
"""


import os
import shutil
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
LOCAL_TASK_ROOT = ROOT_DIR / "tasks"
HIDDEN_ROOT = Path(os.environ.get("HIDDEN_ROOT", "/donotaccess"))
AGENT_USER = "agent"
AGENT_GROUP = "agent"

# Agent-facing files copied into the workspace (mirrors the Dockerfile baseline build).
# `donotaccess` and the calibration helper are NEVER copied into the agent's tree.
AGENT_FILES = ("Makefile", "filelist.f", "prompt.md", "rtl", "dv", "synth", "scripts", "formal", "vendor")
_KEEP = {".hud"}  # the Workspace's ssh-credential dir, never wiped

# golden_pass self-test overlay per track: (src relative to hidden dir, dst relative to
# workspace root). Used by the no-agent validation driver.
GOLDEN_OVERLAY = {
    "stream_arb_fifo_repair": ("stream_arb_fifo_golden.sv", "rtl/stream_arb_fifo.sv"),
    "stream_arb_fifo_cocotb_dv": ("solution/test_stream_arb_fifo.py", "dv/cocotb/test_stream_arb_fifo.py"),
    "stream_arb_fifo_formal": ("solution/stream_arb_fifo_props.sv", "formal/stream_arb_fifo_props.sv"),
}


def _resolve_workspace_root() -> Path:
    explicit = os.environ.get("WORKSPACE_ROOT")
    if explicit:
        return Path(explicit)
    if Path("/workdir").is_dir():  # built image
        return Path("/workdir")
    # LocalRuntime (subprocess): a per-process scratch dir OUTSIDE the repo, so git/pytest
    # don't climb into the project and the repo isn't mutated by edits.
    root = Path(tempfile.gettempdir()) / "hud-verilog-template" / f"workdir-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)
    return root


WORKSPACE_ROOT = _resolve_workspace_root()


def hidden_dir(task_id: str) -> Path:
    candidate = HIDDEN_ROOT / task_id
    if candidate.is_dir():
        return candidate
    return LOCAL_TASK_ROOT / task_id / "donotaccess"


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _make_agent_writable(path: Path) -> None:
    """chown the workspace to the agent uid so the uid-dropped shell can edit it (image only)."""
    if not _is_root():
        return
    for item in [path, *path.rglob("*")]:
        if item.name in _KEEP:
            continue
        try:
            shutil.chown(item, user=AGENT_USER, group=AGENT_GROUP)
            item.chmod(0o755 if item.is_dir() else 0o644)
        except (LookupError, PermissionError, FileNotFoundError):
            pass


def _clear_workspace(workdir: Path) -> None:
    for child in workdir.iterdir():
        if child.name in _KEEP:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _copy_into(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _populate_from_repo(task_id: str, workdir: Path) -> None:
    """LocalRuntime: build the workspace from the repo's agent-facing task files."""
    src = LOCAL_TASK_ROOT / task_id
    for name in AGENT_FILES:
        item = src / name
        if not item.exists():
            continue
        target = workdir / name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    (workdir / "scripts" / "check_calibration.py").unlink(missing_ok=True)


def setup_task(task_id: str, validate_mode: str | None = None) -> dict[str, object]:
    """Reset the workspace to the task's pristine baseline (image: baked; local: from repo)."""
    workdir = WORKSPACE_ROOT
    hidden = hidden_dir(task_id)
    baked_baseline = HIDDEN_ROOT / task_id / "baseline"

    workdir.mkdir(parents=True, exist_ok=True)
    _clear_workspace(workdir)
    if baked_baseline.is_dir():
        _copy_into(baked_baseline, workdir)  # built image
    else:
        _populate_from_repo(task_id, workdir)  # local subprocess

    if validate_mode == "golden_pass" and task_id in GOLDEN_OVERLAY:
        src_rel, dst_rel = GOLDEN_OVERLAY[task_id]
        src = hidden / src_rel
        dst = workdir / dst_rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    _make_agent_writable(workdir)

    return {
        "success": workdir.is_dir(),
        "task_id": task_id,
        "workdir": str(workdir),
        "hidden_dir": str(hidden),
        "validate_mode": validate_mode,
        "baseline_reset": True,
    }
