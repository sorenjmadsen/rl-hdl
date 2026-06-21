#!/usr/bin/env python3

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Privilege-drop prefix for executing AGENT-AUTHORED logic (the formal props, driven via the
# trusted hidden runner). In the deployed image the grader runs as root with the answer key
# at /donotaccess (root:700); dropping to uid 1000 (`agent`) means the props/sby cannot read
# the golden/mutants/rubric. Locally (non-root dev) this is a no-op.
_drop = (
    ["setpriv", "--reuid", "1000", "--regid", "1000", "--clear-groups", "--"]
    if (hasattr(os, "geteuid") and os.geteuid() == 0)
    else []
)


def _chown_tree_to_agent(path: Path) -> None:
    """chown a staged work tree to uid/gid 1000 so the dropped subprocess can use it
    (image/root only; no-op locally)."""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        return
    for item in [path, *path.rglob("*")]:
        try:
            os.chown(item, 1000, 1000)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            pass


def _run_failclosed(
    args: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    """Fail-closed runner for agent-driven code: a timeout SIGKILLs the whole process group
    (start_new_session=True) and returns a non-zero CompletedProcess rather than letting
    TimeoutExpired propagate out of grade(). A hung/timed-out proof scores as not-passed
    (reward 0) and leaves no orphaned sby/yosys/z3 children."""
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, proc.returncode, stdout, None)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            stdout, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            stdout = ""
        return subprocess.CompletedProcess(
            args,
            proc.returncode if proc.returncode is not None else -signal.SIGKILL,
            (stdout or "") + f"\n[grader] timed out after {timeout}s; process group killed\n",
            None,
        )
MUTANTS = [
    "stream_arb_fifo_lane1_starved.sv",
    "stream_arb_fifo_no_full_pop_push.sv",
    "stream_arb_fifo_rr_stuck_lane0.sv",
    "stream_arb_fifo_reset_pref_lane1.sv",
    "stream_arb_fifo_bad_data_mux.sv",
]


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("LC_ALL", None)
    env["LANG"] = "en_US.UTF-8"
    env["LC_CTYPE"] = "en_US.UTF-8"
    # When the grader is root (deployed image), subprocesses are dropped to uid 1000; give
    # them an accessible HOME so child Path.home() lookups don't hit /root (mode 700 -> the
    # dropped child would PermissionError statting /root/...). No-op locally (non-root).
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        env["HOME"] = "/home/agent"
    if platform.system() == "Darwin":
        path_parts = []
        for candidate in [
            Path("/opt/homebrew/bin"),
            Path.home() / "utils" / "oss-cad-suite" / "bin",
        ]:
            if candidate.is_dir():
                path_parts.append(str(candidate))
        path_parts.extend(["/usr/bin", "/bin", "/usr/sbin", "/sbin"])
        path_parts.append(env.get("PATH", ""))
        env["PATH"] = ":".join(part for part in path_parts if part)
    elif (Path.home() / "utils" / "oss-cad-suite" / "bin").is_dir():
        env["PATH"] = f"{Path.home() / 'utils' / 'oss-cad-suite' / 'bin'}:{env.get('PATH', '')}"
    return env


def run_formal(
    root: Path,
    hidden_root: Path,
    rtl: Path,
    props: Path,
    label: str,
    mode: str,
    timeout: int = 180,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"stream-arb-formal-{label}-") as td:
        work = Path(td)
        build_dir = work / "build"
        # The DUT under proof (golden/mutant) lives in /donotaccess (root:700), and the
        # trusted hidden runner does too: both are unreadable by uid 1000. Stage agent-
        # readable copies into the temp dir so the dropped sby process can read them. The
        # props + vendor/filelist come from `root` (the workspace, agent-readable).
        runner = work / "run_formal_hidden.py"
        rtl_copy = work / "dut.sv"
        shutil.copy2(hidden_root / "run_formal_hidden.py", runner)
        shutil.copy2(rtl, rtl_copy)
        _chown_tree_to_agent(work)
        # Invoke the TRUSTED hidden runner (never the agent-editable scripts/run_formal.py),
        # uid-dropped to 1000. --root supplies filelist.f/vendor from the workspace.
        result = _run_failclosed(
            [
                *_drop,
                sys.executable,
                str(runner),
                "--root",
                str(root),
                "--mode",
                mode,
                "--rtl",
                str(rtl_copy),
                "--props",
                str(props),
                "--build-dir",
                str(build_dir),
            ],
            cwd=work,
            env=tool_env(),
            timeout=timeout,
        )
        return {
            "label": label,
            "mode": mode,
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "log": result.stdout[-6000:],
        }


def hygiene_score(props: Path) -> dict[str, object]:
    text = props.read_text(encoding="utf-8")
    suspicious = []
    for pattern in ["/donotaccess", "donotaccess", "stream_arb_fifo_golden", "mutants"]:
        if pattern in text:
            suspicious.append(pattern)
    unsupported = []
    for pattern in ["property ", "endproperty", "sequence ", "endsequence", "assert property"]:
        if pattern in text:
            unsupported.append(pattern.strip())
    has_assert = "assert(" in text or "assert (" in text
    has_assume_or_reset_constraint = "assume(" in text or "assume (" in text or "reset_i <=" in text
    has_cover = "cover(" in text or "cover (" in text
    score = (
        1.0
        if not suspicious
        and not unsupported
        and has_assert
        and has_assume_or_reset_constraint
        and has_cover
        else 0.0
    )
    return {
        "score": score,
        "suspicious_patterns": suspicious,
        "unsupported_sva_patterns": unsupported,
        "has_assert": has_assert,
        "has_assume_or_reset_constraint": has_assume_or_reset_constraint,
        "has_cover": has_cover,
    }


def grade(
    root: Path,
    props_override: Path | None = None,
    hidden_root: Path | None = None,
    rtl_override: Path | None = None,
) -> dict[str, object]:
    hidden_root = hidden_root or root / "donotaccess"
    props = props_override or root / "formal" / "stream_arb_fifo_props.sv"
    golden_rtl = rtl_override or hidden_root / "stream_arb_fifo_golden.sv"

    golden = run_formal(root, hidden_root, golden_rtl, props, "golden", "prove")
    golden_raw = 1.0 if golden["passed"] else 0.0

    cover = run_formal(root, hidden_root, golden_rtl, props, "golden-cover", "cover")
    cover_raw = 1.0 if cover["passed"] else 0.0

    mutant_results = []
    killed = 0
    if golden["passed"]:
        for mutant_name in MUTANTS:
            mutant_result = run_formal(
                root,
                hidden_root,
                hidden_root / "mutants" / mutant_name,
                props,
                mutant_name.removesuffix(".sv"),
                "prove",
            )
            mutant_result["killed"] = not mutant_result["passed"]
            killed += 1 if mutant_result["killed"] else 0
            mutant_results.append(mutant_result)
    mutant_raw = killed / len(MUTANTS)

    hygiene = hygiene_score(props)
    hygiene_raw = float(hygiene["score"])

    reward = round(
        0.20 * golden_raw
        + 0.65 * mutant_raw
        + 0.10 * cover_raw
        + 0.05 * hygiene_raw,
        6,
    )
    hard_caps = []
    if not golden["passed"]:
        reward = 0.0
        hard_caps.append("golden_proof_failed")

    return {
        "reward": reward,
        "hard_caps": hard_caps,
        "subscores": {
            "golden_prove": {
                "weight": 0.20,
                "raw_score": golden_raw,
                "weighted_score": 0.20 * golden_raw,
                "result": golden,
            },
            "mutant_kill": {
                "weight": 0.65,
                "raw_score": mutant_raw,
                "weighted_score": 0.65 * mutant_raw,
                "result": {
                    "killed": killed,
                    "total": len(MUTANTS),
                    "mutants": mutant_results,
                },
            },
            "non_vacuity_cover": {
                "weight": 0.10,
                "raw_score": cover_raw,
                "weighted_score": 0.10 * cover_raw,
                "result": cover,
            },
            "hygiene": {
                "weight": 0.05,
                "raw_score": hygiene_raw,
                "weighted_score": 0.05 * hygiene_raw,
                "result": hygiene,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--props", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    result = grade(args.root.resolve(), props_override=args.props)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if float(result["reward"]) >= 0.999 else 1


if __name__ == "__main__":
    raise SystemExit(main())
