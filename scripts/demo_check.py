"""Local preflight for the hackathon demo.

This does not call Modal or Fireworks. It checks recorded artifacts and runs the
offline flywheel smoke so the presenter can quickly confirm the demo story before
starting live commands.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: str) -> dict:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _ok(label: str, detail: str) -> None:
    print(f"[ok]   {label}: {detail}")


def _warn(label: str, detail: str) -> None:
    print(f"[warn] {label}: {detail}")


def _fail(label: str, detail: str) -> None:
    print(f"[fail] {label}: {detail}")


def _check_pass_at_1(path: str, label: str, minimum: float) -> bool:
    try:
        data = _load_json(path)
    except Exception as exc:  # noqa: BLE001
        _fail(label, f"missing/unreadable {path}: {exc}")
        return False
    pass_at_1 = float(data.get("pass_at_1", -1.0))
    mean_reward = float(data.get("mean_reward", -1.0))
    if pass_at_1 >= minimum:
        _ok(label, f"pass@1={pass_at_1:.3f}, mean_reward={mean_reward:.3f}")
        return True
    _fail(label, f"pass@1={pass_at_1:.3f}, mean_reward={mean_reward:.3f}, expected >= {minimum:.3f}")
    return False


def _check_rft_summary() -> bool:
    try:
        data = _load_json("data/rft_job_h8q9sbpg_summary.json")
    except Exception as exc:  # noqa: BLE001
        _fail("RFT job summary", f"missing/unreadable summary: {exc}")
        return False
    state = data.get("state")
    output_model = data.get("output_model")
    if state == "JOB_STATE_COMPLETED" and output_model:
        _ok("RFT job summary", f"{state}, output={output_model}")
        return True
    _fail("RFT job summary", f"state={state!r}, output={output_model!r}")
    return False


def _check_deployed_rft_eval() -> bool:
    try:
        data = _load_json("data/rft_eval_deployed_heldout.json")
    except Exception as exc:  # noqa: BLE001
        _warn("deployed RFT heldout", f"no recorded eval yet: {exc}")
        return True
    pass_at_1 = float(data.get("pass_at_1", -1.0))
    mean_reward = float(data.get("mean_reward", -1.0))
    if pass_at_1 > 0:
        _ok("deployed RFT heldout", f"pass@1={pass_at_1:.3f}, mean_reward={mean_reward:.3f}")
    else:
        _warn(
            "deployed RFT heldout",
            f"pass@1={pass_at_1:.3f}, mean_reward={mean_reward:.3f}; do not claim RFT quality",
        )
    return True


def _check_tpu_optimization_artifact() -> bool:
    paths = [
        ROOT / "docs/tpu_matmul_optimization/README.md",
        ROOT / "docs/tpu_matmul_optimization/before.v",
        ROOT / "docs/tpu_matmul_optimization/after.v",
    ]
    missing = [str(p.relative_to(ROOT)) for p in paths if not p.exists()]
    if missing:
        _fail("TPU optimization artifact", "missing " + ", ".join(missing))
        return False
    text = paths[0].read_text(encoding="utf-8")
    required = ["1460", "452", "1008", "69.0%"]
    absent = [token for token in required if token not in text]
    if absent:
        _fail("TPU optimization artifact", "missing expected result tokens: " + ", ".join(absent))
        return False
    _ok("TPU optimization artifact", "baseline 1460 -> loop 452 cells; gap 1008")
    return True


def _check_offline_flywheel() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "harness.flywheel"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0 and "demo ok" in out:
        line = next((line for line in out.splitlines() if "demo ok" in line), out.splitlines()[-1])
        _ok("offline flywheel", line)
        return True
    _fail("offline flywheel", out[-1000:] or f"exit {proc.returncode}")
    return False


def main() -> int:
    print("rl-hdl demo preflight\n")
    checks = [
        _check_pass_at_1("data/demo_selftest_gradient.json", "TPU/NPU gradient selftest", 1.0),
        _check_pass_at_1("data/fireworks_inference_kimi_heldout.json", "Fireworks Kimi heldout eval", 1.0),
        _check_rft_summary(),
        _check_deployed_rft_eval(),
        _check_tpu_optimization_artifact(),
        _check_offline_flywheel(),
    ]
    print("\nDemo framing:")
    print("- Lead with verifiable rewards: Verilator/Yosys, no LLM judge.")
    print("- Show RFT as completed and deployed, not as a quality win yet.")
    print("- Use docs/demo_runbook.md for the exact live command sequence.")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
