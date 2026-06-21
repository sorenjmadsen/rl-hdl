#!/usr/bin/env python3

import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_RE = re.compile(r"^SCENARIO\s+(?P<name>\S+)\s+(?P<status>PASS|FAIL)")

# Privilege-drop prefix for executing AGENT-AUTHORED code. The repair sim is compiled from
# the agent's RTL, so a malicious $fopen/$readmemh/$system in that RTL runs when the sim
# executes. In the deployed image the grader runs as root with the answer key at
# /donotaccess (root:700); dropping the sim to uid 1000 (`agent`) walls it out of the key.
# Locally (non-root dev) this is a no-op. (The verilator/yosys COMPILE stays as root.)
_drop = (
    ["setpriv", "--reuid", "1000", "--regid", "1000", "--clear-groups", "--"]
    if (hasattr(os, "geteuid") and os.geteuid() == 0)
    else []
)


def _chown_tree_to_agent(path: Path) -> None:
    """chown a staged work tree to uid/gid 1000 so the dropped sim can read/run it
    (image/root only; no-op locally)."""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        return
    for item in [path, *path.rglob("*")]:
        try:
            os.chown(item, 1000, 1000)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            pass


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("LC_ALL", None)
    env["LANG"] = "en_US.UTF-8"
    env["LC_CTYPE"] = "en_US.UTF-8"
    # When the grader is root (deployed image), the sim is dropped to uid 1000; give it an
    # accessible HOME so child Path.home() lookups don't hit /root (mode 700 -> the dropped
    # child would PermissionError statting /root/...). No-op locally (non-root).
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        env["HOME"] = "/home/agent"

    if platform.system() == "Darwin":
        path_parts = []
        homebrew_bin = Path("/opt/homebrew/bin")
        oss_bin = Path.home() / "utils" / "oss-cad-suite" / "bin"
        if homebrew_bin.is_dir():
            path_parts.append(str(homebrew_bin))
        if oss_bin.is_dir():
            path_parts.append(str(oss_bin))
        path_parts.extend(["/usr/bin", "/bin", "/usr/sbin", "/sbin"])
        path_parts.append(env.get("PATH", ""))
        env["PATH"] = ":".join(part for part in path_parts if part)
        env["AR"] = "/usr/bin/ar"
        env["RANLIB"] = "/usr/bin/ranlib"
    else:
        oss_bin = Path.home() / "utils" / "oss-cad-suite" / "bin"
        if oss_bin.is_dir():
            env["PATH"] = f"{oss_bin}:{env.get('PATH', '')}"
    return env


def run(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Fail-closed runner: a timeout SIGKILLs the whole process group
    (start_new_session=True) and returns a non-zero CompletedProcess rather than letting
    TimeoutExpired propagate out of grade(). A hung compile/sim therefore scores as
    not-passed (reward 0) and leaves no orphaned verilator/sim children."""
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


def count_cells(json_path: Path, cell_type: str | None = None) -> int:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    count = 0
    for module in data.get("modules", {}).values():
        for cell in module.get("cells", {}).values():
            if cell_type is None or cell.get("type") == cell_type:
                count += 1
    return count


def functional_score(rtl: Path, hidden_tb: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="stream-arb-fifo-func-") as td:
        work = Path(td)
        rtl_copy = work / "stream_arb_fifo.sv"
        tb_copy = work / "hidden_tb.sv"
        shutil.copy2(rtl, rtl_copy)
        shutil.copy2(hidden_tb, tb_copy)

        compile_result = run(
            [
                "verilator",
                "--binary",
                "--timing",
                "-Wno-fatal",
                "--top-module",
                "stream_arb_fifo_hidden_tb",
                "-Mdir",
                "obj_hidden",
                "-o",
                "sim_hidden",
                str(rtl_copy),
                str(tb_copy),
            ],
            cwd=work,
            timeout=90,
        )
        if compile_result.returncode != 0:
            return {
                "score": 0.0,
                "passed": 0,
                "total": 4,
                "detail": "Verilator hidden simulation compile failed",
                "log": compile_result.stdout,
            }

        # The hidden testbench is now compiled into the sim binary; its SOURCE must not
        # remain readable by the uid-1000 sim process (it would otherwise leak the expected
        # behaviour / scenario oracle). Delete the staged copy before dropping privileges.
        tb_copy.unlink(missing_ok=True)
        # Hand the work dir (sim binary + RTL copy) to uid 1000 so the dropped sim can run;
        # malicious $fopen/$readmemh/$system in the agent RTL then can't read /donotaccess.
        _chown_tree_to_agent(work)
        sim = work / "obj_hidden" / "sim_hidden"
        sim_result = run([*_drop, str(sim)], cwd=work, timeout=30)
        scenario_status: dict[str, str] = {}
        for line in sim_result.stdout.splitlines():
            match = SCENARIO_RE.match(line.strip())
            if match:
                scenario_status[match.group("name")] = match.group("status")

        total = 4
        passed = sum(1 for status in scenario_status.values() if status == "PASS")
        if sim_result.returncode != 0:
            detail = "hidden simulation exited nonzero"
        elif len(scenario_status) != total:
            detail = f"expected {total} scenarios, saw {len(scenario_status)}"
        else:
            detail = "hidden simulation completed"

        return {
            "score": passed / total,
            "passed": passed,
            "total": total,
            "scenarios": scenario_status,
            "detail": detail,
            "log": sim_result.stdout,
        }


def synthesis_score(rtl: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="stream-arb-fifo-synth-") as td:
        work = Path(td)
        rtl_copy = work / "stream_arb_fifo.sv"
        shutil.copy2(rtl, rtl_copy)

        script = (
            "read_verilog -sv stream_arb_fifo.sv; "
            "hierarchy -top stream_arb_fifo; "
            "proc; opt; write_json proc.json; "
            "synth_ice40 -top stream_arb_fifo -json synth_ice40.json"
        )
        result = run(["yosys", "-q", "-p", script], cwd=work, timeout=60)

        success = result.returncode == 0 and (work / "proc.json").is_file()
        latch_count = None
        cell_count = None
        if success:
            latch_count = count_cells(work / "proc.json", "$dlatch")
            if (work / "synth_ice40.json").is_file():
                cell_count = count_cells(work / "synth_ice40.json")

        latch_free = bool(success and latch_count == 0)
        gate_in_band = bool(success and cell_count is not None and 60 <= cell_count <= 1400)
        weighted = 0.0
        weighted += 0.10 if success else 0.0
        weighted += 0.10 if latch_free else 0.0
        weighted += 0.10 if gate_in_band else 0.0

        return {
            "score": weighted,
            "synthesis_success": success,
            "latch_count": latch_count,
            "cell_count": cell_count,
            "gate_band": [60, 1400],
            "gate_in_band": gate_in_band,
            "detail": "synthesis completed" if success else "synthesis failed",
            "log": result.stdout,
        }


def lint_score(rtl: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="stream-arb-fifo-lint-") as td:
        work = Path(td)
        rtl_copy = work / "stream_arb_fifo.sv"
        shutil.copy2(rtl, rtl_copy)
        result = run(
            [
                "verilator",
                "--lint-only",
                "-Wall",
                "-Wno-fatal",
                "--top-module",
                "stream_arb_fifo",
                str(rtl_copy),
            ],
            cwd=work,
            timeout=30,
        )
        warning_lines = [
            line for line in result.stdout.splitlines() if line.startswith("%Warning-")
        ]
        score = 1.0 if result.returncode == 0 and not warning_lines else 0.0
        return {
            "score": score,
            "warning_count": len(warning_lines),
            "warnings": warning_lines,
            "detail": "lint clean" if score == 1.0 else "lint warnings present",
            "log": result.stdout,
        }


def grade(
    root: Path,
    rtl_override: Path | None,
    hidden_root: Path | None = None,
) -> dict[str, object]:
    rtl = rtl_override if rtl_override is not None else root / "rtl" / "stream_arb_fifo.sv"
    if hidden_root is None:
        local_hidden_root = root / "donotaccess"
        hidden_root = local_hidden_root if local_hidden_root.is_dir() else Path(__file__).parent
    hidden_tb = hidden_root / "hidden_tb.sv"

    functional = functional_score(rtl, hidden_tb)
    synthesis = synthesis_score(rtl)
    lint = lint_score(rtl)

    functional_weighted = 0.50 * float(functional["score"])
    synthesis_weighted = float(synthesis["score"])
    lint_weighted = 0.20 * float(lint["score"])
    reward = round(functional_weighted + synthesis_weighted + lint_weighted, 6)
    hard_caps: list[str] = []
    if float(functional["score"]) == 0.0:
        reward = 0.0
        hard_caps.append("functional_score_zero")

    return {
        "reward": reward,
        "hard_caps": hard_caps,
        "subscores": {
            "functional": {
                "weight": 0.50,
                "raw_score": functional["score"],
                "weighted_score": functional_weighted,
                "result": functional,
            },
            "synthesis": {
                "weight": 0.30,
                "weighted_score": synthesis_weighted,
                "result": synthesis,
            },
            "lint": {
                "weight": 0.20,
                "raw_score": lint["score"],
                "weighted_score": lint_weighted,
                "result": lint,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT), help="task root directory")
    parser.add_argument("--rtl", default=None, help="alternate stream_arb_fifo.sv to grade")
    parser.add_argument(
        "--hidden-root",
        default=None,
        help="directory containing hidden_tb.sv and hidden grader assets",
    )
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    parser.add_argument(
        "--fail-below",
        type=float,
        default=None,
        help="exit nonzero when reward is below this threshold",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    rtl_override = Path(args.rtl).resolve() if args.rtl else None
    hidden_root = Path(args.hidden_root).resolve() if args.hidden_root else None
    result = grade(root, rtl_override, hidden_root)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    if args.fail_below is not None and float(result["reward"]) < args.fail_below:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
