"""Sweep candidate PRs with generated Yosys rewards on Modal.

The sweep records two reward types:

- `yosys_synth`: base RTL fails Yosys parse/synthesis while the PR gold passes.
- `yosys_equiv`: both base and gold synthesize, but a generated Yosys
  miter/equivalence check fails for the base against the gold reference.

These are not replacements for behavioral Verilator/cocotb proofs. They are a
separate generated-reward pass for finding additional candidates that match the
project's candidate-vs-golden seam.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import PurePosixPath

import modal

app = modal.App("rl-hdl-yosys-gradient-sweep")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ca-certificates", "git", "yosys")
    .add_local_file("data/yosys_pr_candidates.json", remote_path="/root/yosys_pr_candidates.json")
)

VERILOG_EXTS = (".v", ".sv")
HEADER_EXTS = (".vh", ".svh")
MAX_FILE_BYTES = 250_000
DEFAULT_MAX_MODULES_PER_PR = 10


def _run(cmd: list[str], cwd, *, timeout: int = 120, input_text: str | None = None) -> dict:
    import subprocess

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def _shell_quote(s: str) -> str:
    # This string is parsed by Yosys, not by a shell. Backslash-escape the
    # characters that matter for the simple file/module tokens we emit here.
    return s.replace("\\", "\\\\").replace(" ", "\\ ")


def _module_names(text: str) -> list[str]:
    import re

    names = []
    for match in re.finditer(r"(?m)^\s*module\s+([a-zA-Z_][a-zA-Z0-9_$]*)\b", text):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return names


def _safe_module_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


def _include_flags(root, source_file: str) -> str:
    dirs = {
        ".",
        str(PurePosixPath(source_file).parent),
        "rtl",
        "rtl/include",
        "src",
        "hdl",
        "hw",
        "hw/rtl",
        "design",
    }
    flags = []
    for d in sorted(dirs):
        if (root / d).exists():
            flags.append(f"-I{_shell_quote(str(root / d))}")
    return " ".join(flags)


def _read_text(path) -> str | None:
    try:
        if not path.exists() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _yosys(root, script: str, *, timeout: int = 180) -> dict:
    return _run(["yosys", "-Q", "-q", "-p", script], root, timeout=timeout)


def _synth_module(root, source_file: str, module: str) -> dict:
    path = root / source_file
    flags = _include_flags(root, source_file)
    script = (
        f"read_verilog -sv {flags} {_shell_quote(str(path))}; "
        f"hierarchy -check -top {_shell_quote(module)}; "
        "proc; opt; flatten; opt; check"
    )
    return _yosys(root, script)


def _synth_file(root, source_file: str) -> dict:
    path = root / source_file
    flags = _include_flags(root, source_file)
    script = f"read_verilog -sv {flags} {_shell_quote(str(path))}; proc; opt; check"
    return _yosys(root, script)


def _equiv_module(base_root, gold_root, source_file: str, module: str) -> dict:
    base_file = base_root / source_file
    gold_file = gold_root / source_file
    base_name = "base_" + _safe_module_name(module)
    gold_name = "gold_" + _safe_module_name(module)
    flags_base = _include_flags(base_root, source_file)
    flags_gold = _include_flags(gold_root, source_file)
    script = (
        f"read_verilog -sv {flags_base} {_shell_quote(str(base_file))}; "
        f"hierarchy -check -top {_shell_quote(module)}; proc; opt; flatten; opt; "
        f"rename {_shell_quote(module)} {_shell_quote(base_name)}; "
        "design -stash base; design -reset; "
        f"read_verilog -sv {flags_gold} {_shell_quote(str(gold_file))}; "
        f"hierarchy -check -top {_shell_quote(module)}; proc; opt; flatten; opt; "
        f"rename {_shell_quote(module)} {_shell_quote(gold_name)}; "
        "design -stash gold; design -reset; "
        f"design -copy-from base -as {_shell_quote(base_name)} {_shell_quote(base_name)}; "
        f"design -copy-from gold -as {_shell_quote(gold_name)} {_shell_quote(gold_name)}; "
        f"equiv_make {_shell_quote(gold_name)} {_shell_quote(base_name)} equiv; "
        "hierarchy -top equiv; proc; opt; equiv_simple -seq 8; equiv_status -assert"
    )
    return _yosys(base_root, script, timeout=240)


def _commit_exists(repo, sha: str) -> bool:
    return _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], repo)["returncode"] == 0


def _commit_parents(repo, sha: str) -> list[str]:
    proc = _run(["git", "show", "-s", "--format=%P", sha], repo)
    if proc["returncode"] != 0:
        return []
    return proc["stdout"].strip().split()


def _try_fetch(repo, sha: str) -> None:
    if sha and not _commit_exists(repo, sha):
        _run(["git", "fetch", "--depth", "1", "origin", sha], repo, timeout=180)


def _add_worktree(repo, path, sha: str) -> dict:
    if path.exists():
        _run(["rm", "-rf", str(path)], repo)
    return _run(["git", "-C", str(repo), "worktree", "add", "--detach", str(path), sha], repo, timeout=180)


def _verify_candidate(repo, tmp_root, candidate: dict, require_tests: bool, max_modules_per_pr: int) -> dict:
    import shutil

    if require_tests and not candidate.get("test_files"):
        return {**candidate, "verdict": "unsuitable", "reason": "no test/harness files in PR"}

    merge_sha = candidate.get("merge_commit_sha") or candidate.get("head_sha")
    _try_fetch(repo, merge_sha)
    gold_sha = merge_sha if _commit_exists(repo, merge_sha) else candidate.get("head_sha")
    _try_fetch(repo, gold_sha)
    parents = _commit_parents(repo, gold_sha)
    base_sha = parents[0] if parents else candidate.get("base_api_sha")
    _try_fetch(repo, base_sha)

    work = tmp_root / f"pr_{candidate['pr']}"
    base_root = work / "base"
    gold_root = work / "gold"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    base_add = _add_worktree(repo, base_root, base_sha)
    gold_add = _add_worktree(repo, gold_root, gold_sha)
    if base_add["returncode"] != 0 or gold_add["returncode"] != 0:
        return {
            **candidate,
            "base_sha": base_sha,
            "gold_sha": gold_sha,
            "verdict": "build_broken",
            "phase_a_result": "worktree add failed",
            "phase_b_result": "not run",
            "log": (base_add["stdout"] + base_add["stderr"] + gold_add["stdout"] + gold_add["stderr"])[-4000:],
        }

    checked = []
    module_limit = max_modules_per_pr if max_modules_per_pr > 0 else 1_000_000
    verified = None
    try:
        for source_file in candidate.get("source_files", []):
            if not source_file.lower().endswith(VERILOG_EXTS):
                continue
            if len(checked) >= module_limit:
                break

            base_file = base_root / source_file
            gold_file = gold_root / source_file
            gold_text = _read_text(gold_file)
            base_text = _read_text(base_file)
            if gold_text is None:
                continue

            gold_modules = _module_names(gold_text)
            base_modules = _module_names(base_text or "")
            common = [m for m in gold_modules if m in base_modules]

            if base_text is None and gold_modules:
                gold_synth = _synth_file(gold_root, source_file)
                checked.append(
                    {
                        "source_file": source_file,
                        "module": gold_modules[0],
                        "reward_type": "yosys_synth",
                        "phase_a_pass": False,
                        "phase_b_pass": gold_synth["returncode"] == 0,
                        "phase_a_result": "base file missing or too large",
                        "phase_b_result": "gold file parsed/synthesized" if gold_synth["returncode"] == 0 else "gold file failed Yosys",
                        "log": (gold_synth["stdout"] + gold_synth["stderr"])[-2000:],
                    }
                )
                if gold_synth["returncode"] == 0:
                    verified = checked[-1]
                    break
                continue

            for module in common[: max(1, module_limit - len(checked))]:
                base_synth = _synth_module(base_root, source_file, module)
                gold_synth = _synth_module(gold_root, source_file, module)
                entry = {
                    "source_file": source_file,
                    "module": module,
                    "base_synth_returncode": base_synth["returncode"],
                    "gold_synth_returncode": gold_synth["returncode"],
                }

                if base_synth["returncode"] != 0 and gold_synth["returncode"] == 0:
                    entry.update(
                        {
                            "reward_type": "yosys_synth",
                            "phase_a_pass": False,
                            "phase_b_pass": True,
                            "phase_a_result": "base module failed Yosys synth/check",
                            "phase_b_result": "gold module passed Yosys synth/check",
                            "log": (base_synth["stdout"] + base_synth["stderr"])[-2000:],
                        }
                    )
                    checked.append(entry)
                    verified = entry
                    break

                if base_synth["returncode"] == 0 and gold_synth["returncode"] == 0:
                    equiv = _equiv_module(base_root, gold_root, source_file, module)
                    entry.update(
                        {
                            "reward_type": "yosys_equiv",
                            "phase_a_pass": equiv["returncode"] == 0,
                            "phase_b_pass": True,
                            "phase_a_result": "base equivalent to gold" if equiv["returncode"] == 0 else "base not equivalent to gold under Yosys miter",
                            "phase_b_result": "gold passed Yosys synth/check",
                            "log": (equiv["stdout"] + equiv["stderr"])[-2000:],
                        }
                    )
                    checked.append(entry)
                    if equiv["returncode"] != 0:
                        verified = entry
                        break
                else:
                    entry.update(
                        {
                            "reward_type": "yosys_synth",
                            "phase_a_pass": base_synth["returncode"] == 0,
                            "phase_b_pass": False,
                            "phase_a_result": "base passed Yosys synth/check" if base_synth["returncode"] == 0 else "base failed Yosys synth/check",
                            "phase_b_result": "gold failed Yosys synth/check",
                            "log": (gold_synth["stdout"] + gold_synth["stderr"])[-2000:],
                        }
                    )
                    checked.append(entry)

            if verified:
                break
    finally:
        _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(base_root)], repo, timeout=120)
        _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(gold_root)], repo, timeout=120)
        shutil.rmtree(work, ignore_errors=True)

    if verified:
        verdict = "verified"
        phase_a = verified["phase_a_result"]
        phase_b = verified["phase_b_result"]
    elif checked and all(not c.get("phase_b_pass") for c in checked):
        verdict = "gold_still_fails"
        phase_a = "checked modules did not produce a base-fail/gold-pass Yosys reward"
        phase_b = "gold failed Yosys on checked modules"
    elif checked and all(c.get("phase_a_pass") for c in checked if c.get("reward_type") == "yosys_equiv"):
        verdict = "base_already_passes"
        phase_a = "checked modules are Yosys-equivalent to gold"
        phase_b = "gold passed Yosys"
    elif checked:
        verdict = "unsuitable"
        phase_a = "checked modules did not produce a clean Yosys gradient"
        phase_b = "gold pass was incomplete or base matched"
    else:
        verdict = "unsuitable"
        phase_a = "no Yosys-checkable Verilog modules found"
        phase_b = "not run"

    return {
        **candidate,
        "base_sha": base_sha,
        "gold_sha": gold_sha,
        "command": "generated yosys synth/equiv miter",
        "checked": checked,
        "phase_a_result": phase_a,
        "phase_b_result": phase_b,
        "verdict": verdict,
        "reward_type": verified.get("reward_type") if verified else None,
        "yosys_source_file": verified.get("source_file") if verified else None,
        "yosys_module": verified.get("module") if verified else None,
    }


@app.function(image=image, timeout=7200)
def sweep_repo(
    repo_name: str,
    candidates: list[dict],
    require_tests: bool = True,
    max_modules_per_pr: int = DEFAULT_MAX_MODULES_PER_PR,
) -> list[dict]:
    import shutil
    from pathlib import Path

    tmp_root = Path("/tmp/rlhdl_yosys") / repo_name.replace("/", "__")
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    tmp_root.mkdir(parents=True)
    repo = tmp_root / "repo"

    clone = _run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", f"https://github.com/{repo_name}.git", str(repo)],
        tmp_root,
        timeout=600,
    )
    if clone["returncode"] != 0:
        return [
            {
                "repo": repo_name,
                "verdict": "build_broken",
                "phase_a_result": "clone failed",
                "phase_b_result": "not run",
                "log": (clone["stdout"] + clone["stderr"])[-4000:],
            }
        ]

    results = []
    for candidate in candidates:
        try:
            results.append(_verify_candidate(repo, tmp_root, candidate, require_tests, max_modules_per_pr))
        except Exception as exc:
            fallback_gold = candidate.get("merge_commit_sha") or candidate.get("head_sha")
            results.append(
                {
                    **candidate,
                    "base_sha": candidate.get("base_api_sha"),
                    "gold_sha": fallback_gold,
                    "command": "generated yosys synth/equiv miter",
                    "verdict": "build_broken",
                    "phase_a_result": f"exception: {type(exc).__name__}",
                    "phase_b_result": "not run",
                    "log": str(exc)[-4000:],
                }
            )
    return results


@app.local_entrypoint()
def main(
    require_tests: bool = True,
    max_prs_per_repo: int = 0,
    max_modules_per_pr: int = DEFAULT_MAX_MODULES_PER_PR,
    only: str = "",
    out: str = "data/yosys_verified_gradients.jsonl",
) -> None:
    from pathlib import Path

    data = json.loads(Path("data/yosys_pr_candidates.json").read_text(encoding="utf-8"))
    only_specs = {item.strip() for item in only.split(",") if item.strip()}
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for candidate in data["candidates"]:
        if require_tests and not candidate.get("test_files"):
            continue
        if only_specs and f"{candidate['repo']}#{candidate['pr']}" not in only_specs:
            continue
        by_repo[candidate["repo"]].append(candidate)

    if max_prs_per_repo:
        by_repo = {repo: rows[:max_prs_per_repo] for repo, rows in by_repo.items()}

    repo_names = list(by_repo)
    result_batches = list(
        sweep_repo.map(
            repo_names,
            [by_repo[r] for r in repo_names],
            [require_tests] * len(repo_names),
            [max_modules_per_pr] * len(repo_names),
        )
    )
    results = [item for batch in result_batches for item in batch]

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    summary = {
        "repos": len(repo_names),
        "candidates": len(results),
        "verdicts": dict(sorted({v: sum(1 for r in results if r.get("verdict") == v) for v in {r.get("verdict") for r in results}}.items())),
        "verified": [
            {
                "repo": r.get("repo"),
                "pr": r.get("pr"),
                "title": r.get("title"),
                "reward_type": r.get("reward_type"),
                "module": r.get("yosys_module"),
                "source_file": r.get("yosys_source_file"),
            }
            for r in results
            if r.get("verdict") == "verified"
        ],
    }
    print(json.dumps(summary, indent=2))
    print(f"wrote {len(results)} rows to {out_path}")
