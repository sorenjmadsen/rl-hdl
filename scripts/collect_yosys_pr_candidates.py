"""Collect merged PR metadata for the Yosys verified-gradient sweep.

This uses the local GitHub CLI auth (`gh api`) because the full candidate set is
large enough to hit unauthenticated GitHub API limits.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

CANDIDATE_REPOS = [
    "Purdue-SoCET/atalla",
    "YashKarthik/tpu",
    "thousrm/universal_NPU-CNN_accelerator",
    "kagandikmen/TPU.sv",
    "bradgrantham/alice5",
    "chipsalliance/Cores-VeeR-EL2",
    "vortexgpgpu/vortex",
]

SOURCE_EXTS = (".v", ".sv", ".svh", ".vh", ".vhd", ".vhdl")
SOURCE_RE = re.compile(r"(^|/)(rtl|src|hdl|hw|design|npu|gpu|src/main/scala)(/|$)", re.I)
TEST_RE = re.compile(
    r"(^|/)(tb|test|tests|sim|verification|verif|unittest|testbench)(/|$)"
    r"|(_tb\.|tb_|test_).*\.(sv|v|cpp|cc|c|py|vh|svh)$",
    re.I,
)


def gh_json(args: list[str]) -> object:
    out = subprocess.check_output(["gh", "api", "-X", "GET", *args], text=True)
    return json.loads(out)


def gh_paginated_json(args: list[str]) -> list[dict]:
    out = subprocess.check_output(["gh", "api", "-X", "GET", *args, "--paginate"], text=True)
    decoder = json.JSONDecoder()
    rows: list[dict] = []
    idx = 0
    while idx < len(out):
        while idx < len(out) and out[idx].isspace():
            idx += 1
        if idx >= len(out):
            break
        item, idx = decoder.raw_decode(out, idx)
        if isinstance(item, list):
            rows.extend(item)
        else:
            rows.append(item)
    return rows


def collect_repo(repo: str) -> tuple[dict, list[dict]]:
    prs = gh_paginated_json([f"repos/{repo}/pulls", "-f", "state=closed", "-f", "per_page=100"])
    merged = [p for p in prs if p.get("merged_at")]
    candidates: list[dict] = []

    for pr in merged:
        files = gh_paginated_json([f"repos/{repo}/pulls/{pr['number']}/files", "-f", "per_page=100"])
        names = [f["filename"] for f in files]
        source_files = [
            n for n in names
            if n.lower().endswith(SOURCE_EXTS) and SOURCE_RE.search(n)
        ]
        test_files = [n for n in names if TEST_RE.search(n)]
        if not source_files:
            continue
        candidates.append(
            {
                "repo": repo,
                "repo_url": f"https://github.com/{repo}",
                "pr": pr["number"],
                "title": pr["title"],
                "merged_at": pr["merged_at"],
                "merge_commit_sha": pr["merge_commit_sha"],
                "head_sha": pr["head"]["sha"],
                "base_api_sha": pr["base"]["sha"],
                "source_files": source_files,
                "test_files": test_files,
                "all_files": names,
            }
        )

    summary = {
        "closed_prs": len(prs),
        "merged_prs": len(merged),
        "rtl_prs": len(candidates),
        "rtl_plus_test_prs": sum(1 for c in candidates if c["test_files"]),
    }
    return summary, candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/yosys_pr_candidates.json")
    parser.add_argument("--repo", action="append", dest="repos", help="owner/repo to collect; defaults to all candidates")
    args = parser.parse_args()

    repos = args.repos or CANDIDATE_REPOS
    summary = {}
    candidates = []
    for repo in repos:
        repo_summary, repo_candidates = collect_repo(repo)
        summary[repo] = repo_summary
        candidates.extend(repo_candidates)
        print(f"{repo}: {repo_summary}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "candidates": candidates}, indent=2), encoding="utf-8")
    print(f"wrote {len(candidates)} candidates to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
