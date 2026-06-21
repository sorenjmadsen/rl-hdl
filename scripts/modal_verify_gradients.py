"""Run verified-gradient proofs on Modal.

Usage:
    modal run scripts/modal_verify_gradients.py

Each candidate is checked as:
base commit, base + test-only patch, and gold commit.  A verified gradient is
base+test FAIL and gold PASS.  The base-as-is result is reported separately so
clean gradients can be preferred over repair commits whose parent was already
failing its older test.
"""

from __future__ import annotations

import json

import modal


app = modal.App("rl-hdl-verified-gradients")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "make", "iverilog")
    .pip_install("cocotb==1.9.2", "numpy==2.1.3", "pytest==8.3.4")
)

CANDIDATES = [
    {
        "id": "tpu_pr6_repeated_matmul",
        "repo_url": "https://github.com/YashKarthik/tpu",
        "pr": 6,
        "title": "Allowed repeated matmul",
        "base_sha": "291f0b4f9d324f4a58f6d01b6109c7b17661927f",
        "gold_sha": "9c579d5e4d316dce739f0074007743c1dc214ab3",
        "test_files": ["test/test.py"],
        "gold_rtl_files": ["src/PE.v", "src/controller.v", "src/systolic_array_2x2.v"],
    },
    {
        "id": "tpu_commit_f4ea139d_initial_passing_test",
        "repo_url": "https://github.com/YashKarthik/tpu",
        "commit": "f4ea139d6486f242dc2f59183c7bc47d053d06cb",
        "title": "the tests work!",
        "base_sha": "05180ed024bbf9a01ee303a0709bd894078933f4",
        "gold_sha": "f4ea139d6486f242dc2f59183c7bc47d053d06cb",
        "test_files": ["test/test.py"],
        "gold_rtl_files": ["src/controller.v", "src/mmu.v", "src/tpu.v"],
    },
    {
        "id": "tpu_commit_6cffeff_real_systolic_array",
        "repo_url": "https://github.com/YashKarthik/tpu",
        "commit": "6cffeff0b1fb340a6352761a94b9570414eb1953",
        "title": "REAL SYSTOLIC ARRAY WORKING!",
        "base_sha": "3697d5d019b37a15ea546ebd25e0d2c4d1afef4f",
        "gold_sha": "6cffeff0b1fb340a6352761a94b9570414eb1953",
        "test_files": ["test/test.py"],
        "gold_rtl_files": ["src/PE.v", "src/controller.v", "src/systolic_array_2x2.v"],
    },
    {
        "id": "tpu_commit_4c2fad9_pr8_first_passing_integrated",
        "repo_url": "https://github.com/YashKarthik/tpu",
        "commit": "4c2fad9a000ac87c1636c6a923cf577f838af486",
        "title": "make tests pass, follow yosys guidance",
        "base_sha": "31e0cb79b92b3ebf12d7168c59a67d13c5f79087",
        "gold_sha": "4c2fad9a000ac87c1636c6a923cf577f838af486",
        "test_files": ["test/test.py"],
        "gold_rtl_files": ["src/PE.v", "src/control_unit.v", "src/memory.v", "src/mmu_feeder.v", "src/tpu.v"],
    },
    {
        "id": "tpu_commit_b85c127_signed_instruction_cleanup",
        "repo_url": "https://github.com/YashKarthik/tpu",
        "commit": "b85c1270d8d03bfcd90b9fbf73789b7cb3c2ef63",
        "title": "clean up instructions",
        "base_sha": "649546e265306ada82f2bc3bf1276f04b83ba257",
        "gold_sha": "b85c1270d8d03bfcd90b9fbf73789b7cb3c2ef63",
        "test_files": ["test/test.py"],
        "gold_rtl_files": ["src/control_unit.v", "src/mmu_feeder.v", "src/tpu.v"],
    },
]


@app.function(image=image, timeout=600)
def verify_tpu_candidate(candidate: dict) -> dict:
    import os
    import shutil
    import site
    import subprocess
    from pathlib import Path

    root = Path(f"/tmp/rlhdl_modal_{candidate['id']}")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    repo = root / "tpu"
    base = root / "base"
    testonly = root / "testonly"
    gold = root / "gold"

    def run(cmd: list[str], cwd: Path, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = site.getsitepackages()[0]
        env["VIRTUAL_ENV"] = "/usr/local"
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)

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
        result = {
            **candidate,
            "verdict": "build_broken",
            "phase_a_result": "test patch did not apply",
            "phase_b_result": "not run",
            "log": (apply_patch.stdout + apply_patch.stderr)[-4000:],
        }
        return result

    command = "make clean && make && ! grep failure results.xml"

    def run_test(path: Path) -> dict:
        clean = run(["make", "clean"], path / "test")
        make = run(["make"], path / "test")
        grep = run(["grep", "failure", "results.xml"], path / "test")
        passed = clean.returncode == 0 and make.returncode == 0 and grep.returncode == 1
        return {
            "passed": passed,
            "returncodes": {"clean": clean.returncode, "make": make.returncode, "grep_failure": grep.returncode},
            "log": (clean.stdout + clean.stderr + make.stdout + make.stderr + grep.stdout + grep.stderr)[-4000:],
        }

    base_original = run_test(base)
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
        "command": command,
        "base_original": base_original,
        "clean_base": base_original["passed"],
        "phase_a": phase_a,
        "phase_b": phase_b,
        "verdict": verdict,
    }


@app.local_entrypoint()
def main() -> None:
    results = list(verify_tpu_candidate.map(CANDIDATES))
    print(json.dumps(results, indent=2))
