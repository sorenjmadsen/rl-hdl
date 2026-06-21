"""Run the NPU verified-gradient proof on Modal.

Usage:
    modal run scripts/modal_npu_gradients.py

The upstream testbench does not call $finish, so the run command uses timeout
and classifies pass/fail from the transcript. The Modal proof bounds the number
of random vectors with a Verilator parameter override to keep the smoke test
cheap while preserving the base+test FAIL / gold PASS check.
"""

from __future__ import annotations

import json

import modal


app = modal.App("rl-hdl-npu-gradients")

image = (
    modal.Image.from_registry(
        "ubuntu:24.04",
        add_python="3.12",
        setup_dockerfile_commands=["ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC"],
    )
    .apt_install("build-essential", "git", "make", "verilator")
)

NPU_PR64 = {
    "id": "npu_pr64_int34_to_fp32",
    "repo_url": "https://github.com/thousrm/universal_NPU-CNN_accelerator",
    "pr": 64,
    "title": "complete designing fp32 converter",
    "base_sha": "f91c413bbd47e9463113ac42bc1000c63e55cfa2",
    "gold_sha": "ec3b1eae14e6cbd6ecc8d61bab7dbfa36828299b",
    "test_files": ["npu_v2/TB/MAC/tb_mac_fp32_converter.sv"],
    "gold_rtl_files": ["npu_v2/RTL/MAC/mac_fp32_converter.sv"],
}


@app.function(image=image, timeout=600)
def verify_npu_candidate(candidate: dict) -> dict:
    import os
    import shutil
    import subprocess
    from pathlib import Path

    root = Path(f"/tmp/rlhdl_modal_{candidate['id']}")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    repo = root / "repo"
    base = root / "base"
    testonly = root / "testonly"
    gold = root / "gold"

    env = os.environ.copy()
    env.pop("VERILATOR_ROOT", None)

    def run(cmd: list[str], cwd: Path, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)

    subprocess.run(
        ["git", "clone", candidate["repo_url"], str(repo)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    base_sha = candidate["base_sha"]
    gold_sha = candidate["gold_sha"]
    for path, sha in ((base, base_sha), (testonly, base_sha), (gold, gold_sha)):
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(path), sha],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

    patch = subprocess.run(
        ["git", "-C", str(repo), "diff", base_sha, gold_sha, "--", *candidate["test_files"]],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout
    apply_patch = subprocess.run(
        ["git", "-C", str(testonly), "apply"],
        input=patch,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if apply_patch.returncode != 0:
        return {
            **candidate,
            "verdict": "build_broken",
            "phase_a_result": "test patch did not apply",
            "phase_b_result": "not run",
            "log": (apply_patch.stdout + apply_patch.stderr)[-4000:],
        }

    command = [
        "verilator",
        "--binary",
        "--timing",
        "-Wno-fatal",
        "-GNUM_RANDOM_TESTS=64",
        "--top-module",
        "tb_mac_fp32_converter",
        "RTL/common/mac_pkg.sv",
        "RTL/common/find_leading_one.sv",
        "RTL/MAC/mac_fp32_converter.sv",
        "TB/MAC/tb_mac_fp32_converter.sv",
    ]

    def run_test(path: Path) -> dict:
        npu_v2 = path / "npu_v2"
        build = run(command, npu_v2, timeout=180)
        if build.returncode != 0:
            return {
                "passed": False,
                "stage": "build",
                "returncodes": {"build": build.returncode, "run": None},
                "failed_lines": 0,
                "passed_lines": 0,
                "log": (build.stdout + build.stderr)[-4000:],
            }

        sim = run(["timeout", "8s", "obj_dir/Vtb_mac_fp32_converter"], npu_v2, timeout=20)
        transcript = sim.stdout + sim.stderr
        failed_lines = transcript.count("Failed")
        passed_lines = transcript.count("Passed")
        passed = failed_lines == 0 and passed_lines > 0
        return {
            "passed": passed,
            "stage": "run",
            "returncodes": {"build": build.returncode, "run": sim.returncode},
            "failed_lines": failed_lines,
            "passed_lines": passed_lines,
            "log": transcript[-4000:],
        }

    phase_a = run_test(testonly)
    phase_b = run_test(gold)

    if not phase_a["passed"] and phase_b["passed"]:
        verdict = "verified"
    elif phase_a["passed"] and phase_b["passed"]:
        verdict = "base_already_passes"
    elif not phase_b["passed"]:
        verdict = "gold_still_fails"
    else:
        verdict = "unsuitable"

    return {
        **candidate,
        "command": "cd npu_v2 && " + " ".join(command) + " && timeout 8s obj_dir/Vtb_mac_fp32_converter",
        "phase_a": phase_a,
        "phase_b": phase_b,
        "verdict": verdict,
    }


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(verify_npu_candidate.remote(NPU_PR64), indent=2))
