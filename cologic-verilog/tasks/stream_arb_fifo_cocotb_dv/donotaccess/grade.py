#!/usr/bin/env python3

import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Privilege-drop prefix for executing AGENT-AUTHORED code (the cocotb testbench). In the
# deployed image the grader runs as root and the hidden answer key lives at /donotaccess
# (root:700); dropping to uid 1000 (`agent`) means agent code the grader executes cannot
# read the golden/mutants/rubric. Locally (non-root dev), this is a no-op.
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
REQUIRED_COVERAGE = [
    "reset",
    "lane0_basic",
    "lane1_only",
    "round_robin_contention",
    "full_pop_push",
    "reset_restarts_arbitration",
    "wraparound_order",
]
MUTANTS = [
    "stream_arb_fifo_lane1_starved.sv",
    "stream_arb_fifo_no_full_pop_push.sv",
    "stream_arb_fifo_rr_stuck_lane0.sv",
    "stream_arb_fifo_reset_pref_lane1.sv",
    "stream_arb_fifo_bad_wrap.sv",
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
        env["AR"] = "/usr/bin/ar"
        env["RANLIB"] = "/usr/bin/ranlib"
    elif (Path.home() / "utils" / "oss-cad-suite" / "bin").is_dir():
        env["PATH"] = f"{Path.home() / 'utils' / 'oss-cad-suite' / 'bin'}:{env.get('PATH', '')}"
    return env


def run(args: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Fail-closed runner for agent-authored code: a timeout SIGKILLs the whole process
    group (start_new_session=True) and returns a non-zero CompletedProcess rather than
    letting TimeoutExpired propagate out of grade(). A hung/timed-out grader therefore
    scores as not-passed (reward 0) and leaves no orphaned verilator/cocotb children."""
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=tool_env(),
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


def vendor_filelist(root: Path, work: Path) -> Path | None:
    source_filelist = root / "filelist.f"
    if not source_filelist.exists():
        return None
    vendor_sources = []
    for raw_line in source_filelist.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("+incdir+") or line.startswith("-I"):
            continue
        source = (root / line).resolve()
        if source.name == "stream_arb_fifo.sv":
            continue
        vendor_sources.append(source)
    if not vendor_sources:
        return None
    generated = work / "vendor_sources.f"
    generated.write_text(
        "".join(f"{source}\n" for source in vendor_sources),
        encoding="utf-8",
    )
    return generated


def run_cocotb(root: Path, hidden_root: Path, rtl: Path, tests: Path, label: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"stream-arb-dv-{label}-") as td:
        work = Path(td)
        rtl_copy = work / "stream_arb_fifo.sv"
        test_dir = work / "tests"
        test_dir.mkdir()
        shutil.copy2(rtl, rtl_copy)
        shutil.copy2(tests, test_dir / "test_stream_arb_fifo.py")
        coverage = work / "coverage.json"
        results = work / "results.xml"
        # The trusted hidden runner lives in /donotaccess (root:700) which uid 1000 cannot
        # read; stage a copy into the work dir so the dropped interpreter can load it. The
        # runner is grader-authored (trusted), only the testbench it imports is agent code.
        runner = work / "run_cocotb_hidden.py"
        shutil.copy2(hidden_root / "run_cocotb_hidden.py", runner)
        filelist = vendor_filelist(root, work)
        # Hand the staged work dir to uid 1000 so the dropped subprocess can read the DUT
        # copy + runner and write build/coverage/results, while still being walled out of
        # /donotaccess (so a testbench that tries to read the golden has no oracle).
        _chown_tree_to_agent(work)
        result = run(
            [
                *_drop,
                sys.executable,
                str(runner),
                "--rtl",
                str(rtl_copy),
                "--tests",
                str(test_dir / "test_stream_arb_fifo.py"),
                *(
                    ["--filelist", str(filelist)]
                    if filelist is not None
                    else []
                ),
                "--include-dir",
                str(root / "vendor" / "basejump_stl" / "bsg_misc"),
                "--build-dir",
                str(work / "build"),
                "--coverage-file",
                str(coverage),
                "--results-xml",
                str(results),
            ],
            cwd=work,
            timeout=180,
        )
        coverage_data: dict[str, bool] = {}
        if coverage.exists():
            try:
                coverage_data = json.loads(coverage.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                coverage_data = {}
        return {
            "label": label,
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "coverage": coverage_data,
            "log": result.stdout[-6000:],
        }


def hygiene_score(testbench: Path) -> dict[str, object]:
    text = testbench.read_text(encoding="utf-8")
    suspicious = []
    for pattern in ["/donotaccess", "donotaccess", "stream_arb_fifo_golden", "run_cocotb_hidden"]:
        if pattern in text:
            suspicious.append(pattern)
    has_cocotb_test = "@cocotb.test" in text
    uses_clock_edges = "RisingEdge" in text or "FallingEdge" in text
    uses_coverage_helper = len(re.findall(r"\bmark_coverage\s*\(", text)) > 1
    score = 1.0 if not suspicious and has_cocotb_test and uses_clock_edges and uses_coverage_helper else 0.0
    return {
        "score": score,
        "suspicious_patterns": suspicious,
        "has_cocotb_test": has_cocotb_test,
        "uses_clock_edges": uses_clock_edges,
        "uses_coverage_helper": uses_coverage_helper,
    }


def grade(
    root: Path,
    rtl_override: Path | None = None,
    hidden_root: Path | None = None,
    test_override: Path | None = None,
) -> dict[str, object]:
    hidden_root = hidden_root or root / "donotaccess"
    testbench = test_override or root / "dv" / "cocotb" / "test_stream_arb_fifo.py"
    golden_rtl = rtl_override or hidden_root / "stream_arb_fifo_golden.sv"

    golden = run_cocotb(root, hidden_root, golden_rtl, testbench, "golden")
    golden_raw = 1.0 if golden["passed"] else 0.0

    mutant_results = []
    killed = 0
    if golden["passed"]:
        for mutant_name in MUTANTS:
            mutant_result = run_cocotb(
                root,
                hidden_root,
                hidden_root / "mutants" / mutant_name,
                testbench,
                mutant_name.removesuffix(".sv"),
            )
            mutant_result["killed"] = not mutant_result["passed"]
            killed += 1 if mutant_result["killed"] else 0
            mutant_results.append(mutant_result)
    mutant_raw = killed / len(MUTANTS)

    coverage_data = golden.get("coverage", {}) if isinstance(golden.get("coverage"), dict) else {}
    covered = [point for point in REQUIRED_COVERAGE if coverage_data.get(point)]
    coverage_raw = len(covered) / len(REQUIRED_COVERAGE)
    hygiene = hygiene_score(testbench)
    hygiene_raw = float(hygiene["score"])

    reward = round(
        0.25 * golden_raw
        + 0.45 * mutant_raw
        + 0.20 * coverage_raw
        + 0.10 * hygiene_raw,
        6,
    )
    hard_caps = []
    if not golden["passed"]:
        reward = 0.0
        hard_caps.append("golden_dut_failed")

    return {
        "reward": reward,
        "hard_caps": hard_caps,
        "subscores": {
            "golden_pass": {
                "weight": 0.25,
                "raw_score": golden_raw,
                "weighted_score": 0.25 * golden_raw,
                "result": golden,
            },
            "mutant_kill": {
                "weight": 0.45,
                "raw_score": mutant_raw,
                "weighted_score": 0.45 * mutant_raw,
                "result": {
                    "killed": killed,
                    "total": len(MUTANTS),
                    "mutants": mutant_results,
                },
            },
            "coverage": {
                "weight": 0.20,
                "raw_score": coverage_raw,
                "weighted_score": 0.20 * coverage_raw,
                "result": {
                    "covered": covered,
                    "required": REQUIRED_COVERAGE,
                    "coverage_data": coverage_data,
                },
            },
            "testbench_hygiene": {
                "weight": 0.10,
                "raw_score": hygiene_raw,
                "weighted_score": 0.10 * hygiene_raw,
                "result": hygiene,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--tests", default=None, help="Alternate CocoTB testbench")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    result = grade(
        Path(args.root).resolve(),
        test_override=Path(args.tests).resolve() if args.tests else None,
    )
    if args.pretty:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, sort_keys=True))
    return 0 if result["reward"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
