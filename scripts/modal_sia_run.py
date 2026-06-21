"""Modal wrapper for the SIA harness-lever loop on the RTL-optimize task.

Turns the loop: SIA's meta/feedback agents evolve the optimizer scaffold
(`reference_target_agent.py`) across generations; each generation the target agent
optimizes the designs and `evaluate.py` scores it with the IMMUTABLE grader
(deployed Verilator + Yosys verifier). The meta/feedback agent runs on Claude
(Agent SDK), the target policy on Fireworks — so both `anthropic-api` and
`fireworks-api` Modal secrets are needed. Verification is toolchain-free here: it
calls the deployed `grade_opt_remote` function.

  modal run scripts/modal_sia_run.py::validate_entry    # cheap: no LLM calls
  modal run scripts/modal_sia_run.py::seed              # harness+verifier, no meta-agent
  modal run scripts/modal_sia_run.py::main --max-gen 2  # full SIA loop (SPENDS Fireworks)

Live stage markers (streamed during a run):
  [HARNESS]   the harness samples a rewrite / runs a repair / updates per generation
  [SIM]       the harness triggers a simulation (deployed Verilator+Yosys verifier)
  [FOOTPRINT] gate-count result so far (ref->cand cells, % smaller, reward)
  [EVAL]      evaluate.py scoring the generation's submission
  [WEIGHTS]   (future) reserved for the weight-update lever (RFT) progress
"""

from __future__ import annotations

import json

import modal

REPO = "/root/rl-hdl"

# NO silicon toolchain here. Verification runs on the DEPLOYED `grade_opt_remote`
# Modal function (which already has Verilator+Yosys); the agent + evaluate.py call
# it by name. So this image is just Python deps + the repo — builds in seconds.
sia_image = (
    modal.Image.debian_slim(python_version="3.11")
    # The Claude Agent SDK (meta agent) drives the Node `claude` CLI under the hood.
    .apt_install("nodejs", "npm")
    .run_commands("npm install -g @anthropic-ai/claude-code")
    # `uv` for SIA's per-generation venv; sia-agent[claude] = the Claude Agent SDK meta
    # impl (the proven one — Fireworks meta loops/won't-install); openai (target) + modal.
    .pip_install("uv", "sia-agent[claude]", "openai>=1.0", "modal>=0.64")
    # The repo: SIA's venv installs cologic editable from here, and the task dir ships.
    .add_local_dir(
        ".", REPO, copy=True,
        ignore=[".git", ".venv", "**/__pycache__", "runs", "data", "*.lock",
                "*.jsonl", "ve_*.json", "*_selftest.json"],
    )
)

app = modal.App("rl-hdl-sia")

TASK_DIR = f"{REPO}/sia_task/rtl-optimize"


@app.function(image=sia_image, timeout=300)
def validate() -> dict:
    """Cheap preflight: image built, sia importable, task/profiles well-formed. No LLM calls."""
    import subprocess
    from pathlib import Path

    def _py(code):
        return subprocess.run(["python", "-c", code], capture_output=True, text=True)

    out = {}
    out["sia_import"] = _py("import sia.orchestrator; print('ok')").stdout.strip() or \
        _py("import sia.orchestrator").stderr.strip()[-200:]
    out["openhands_sdk"] = _py("import openhands.sdk; print('ok')").stdout.strip() or \
        _py("import openhands.sdk").stderr.strip()[-200:]
    out["sia_agent_installed"] = subprocess.run(
        ["pip", "show", "sia-agent"], capture_output=True, text=True).stdout.split("\n")[0:2]
    out["bin_sia"] = subprocess.run(["ls", "-la", "/usr/local/bin/"], capture_output=True, text=True).stdout
    out["bin_sia"] = [ln for ln in out["bin_sia"].splitlines() if "sia" in ln.lower()]

    task = Path(TASK_DIR)
    out["task_md"] = (task / "data/public/task.md").exists()
    out["evaluate_py"] = (task / "data/public/evaluate.py").exists()
    out["reference_agent"] = (task / "reference/reference_target_agent.py").exists()
    out["profiles"] = sorted(p.name for p in (task / "profiles").glob("*.json"))
    out["providers"] = sorted(p.name for p in (task / "providers").glob("*.json"))
    out["public_designs"] = json.loads((task / "data/public/manifest.json").read_text())["designs"]
    # cologic is editable-installable from the repo (what SIA's venv will do)
    rc = subprocess.run(["uv", "pip", "install", "--system", "-e", REPO], capture_output=True, text=True)
    out["cologic_editable_install_rc"] = rc.returncode
    out["cologic_importable"] = subprocess.run(
        ["python", "-c", "import cologic, cologic.grader, cologic.upload; print('ok')"],
        capture_output=True, text=True,
    ).stdout.strip()
    return out


@app.function(image=sia_image, secrets=[modal.Secret.from_name("anthropic-api")], timeout=120)
def claude_check() -> dict:
    """Surface the real Claude CLI error (the SDK hides it behind 'check stderr')."""
    import os
    import subprocess

    out = {"key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
           "key_prefix": os.environ.get("ANTHROPIC_API_KEY", "")[:8]}
    which = subprocess.run(["which", "claude"], capture_output=True, text=True)
    out["claude_path"] = which.stdout.strip() or which.stderr.strip()
    v = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    out["version"] = (v.stdout + v.stderr).strip()[:80]
    sdk_ver = subprocess.run(["python", "-c", "import claude_agent_sdk as c; print(c.__version__)"],
                             capture_output=True, text=True)
    out["claude_agent_sdk"] = (sdk_ver.stdout + sdk_ver.stderr).strip()[:60]
    try:
        # Mimic the SDK's streaming/control mode to surface the real failure.
        p = subprocess.run(
            ["claude", "--print", "--output-format", "stream-json", "--verbose",
             "--model", "sonnet", "--permission-mode", "bypassPermissions", "say OK"],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "IS_SANDBOX": "1"})  # allow --dangerously-skip-permissions as root
        out["stream_rc"] = p.returncode
        out["stream_out"] = p.stdout[-400:]
        out["stream_err"] = p.stderr[-1500:]
    except Exception as e:  # noqa: BLE001
        out["stream_exc"] = str(e)
    return out


@app.local_entrypoint()
def claude_check_entry():
    print(json.dumps(claude_check.remote(), indent=2))


@app.function(image=sia_image,
              secrets=[modal.Secret.from_name("fireworks-api"),   # target (Kimi)
                       modal.Secret.from_name("anthropic-api")],  # meta (Claude Agent SDK)
              timeout=5400, cpu=4.0)
def sia_run_remote(
    max_gen: int, run_id: int, target_model: str, meta_model: str,
    n_candidates: int, temperature: float, max_repair: int, meta_max_turns: int,
    upload: dict | None = None, max_tokens: int = 2048,
) -> dict:
    """Run the full SIA loop (meta agent evolves the scaffold) and return each
    generation's score plus the refined RTL.

    With `upload` (the web flow) it optimizes ONE user-supplied design instead of
    the baked-in public benchmark — see `_prepare_upload_task_dir` for the dataset
    it injects. Without it, it runs the public manifest (the `main` entrypoint).
    """
    import os
    import subprocess
    from pathlib import Path

    # Point SIA at the uploaded design's dataset, or the baked-in public manifest.
    task = _prepare_upload_task_dir(upload, run_id) if upload else Path(TASK_DIR)
    n_designs = len(json.loads((task / "data/public/manifest.json").read_text())["designs"])

    # The target agent runs in SIA's per-generation venv; it needs cologic (Task
    # building from RTL), openai (sampling), and modal (to call the deployed verifier).
    (task / "reference/requirements.txt").write_text(f"openai>=1.0\nmodal>=0.64\n-e {REPO}\n")

    # Inject the chosen models into the profiles (single provider: fireworks).
    _patch_profile(task / "profiles/fireworks-target.json", target_model)
    _patch_profile(task / "profiles/claude-meta.json", meta_model)

    work = Path("/root/work")
    work.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["SIA_PROVIDERS_DIR"] = str(task / "providers")
    env["SIA_PROFILES_DIR"] = str(task / "profiles")
    # Give the meta/feedback agent enough tool turns to read context + write the
    # full target_agent.py (the default cap of 20 is too few).
    env["SIA_MAX_TURNS"] = str(meta_max_turns)
    # Quiet the litellm/httpx per-request chatter so SIA's stage logs + our
    # [HARNESS]/[SIM]/[FOOTPRINT] markers are actually visible in the stream.
    env["LITELLM_LOG"] = "ERROR"
    env["LITELLM_VERBOSE"] = "False"
    # The Claude Agent SDK passes --dangerously-skip-permissions, which the CLI
    # refuses as root (Modal runs as root). IS_SANDBOX=1 is the sanctioned bypass.
    env["IS_SANDBOX"] = "1"
    # Harness knobs the seed agent reads (the search space SIA then evolves).
    env["COLOGIC_TARGET_MODEL"] = target_model
    env["COLOGIC_N_CANDIDATES"] = str(n_candidates)
    env["COLOGIC_TEMPERATURE"] = str(temperature)
    env["COLOGIC_MAX_REPAIR"] = str(max_repair)
    env["COLOGIC_MAX_TOKENS"] = str(max_tokens)

    # Invoke SIA's entry point directly (the console script isn't reliably on PATH and
    # the published package has no __main__); run args fall through as sys.argv.
    cmd = [
        "python", "-c", "from sia.orchestrator import main; main()",
        "run", "--task_dir", str(task), "--max_gen", str(max_gen),
        "--run_id", str(run_id), "--no-web",
        "--meta-agent-profile", "claude-meta",
        "--target-agent-profile", "fireworks-target",
    ]
    print(f"[SIA] launching {max_gen} generations on {n_designs} design(s) "
          f"(target={target_model}, meta={meta_model})\n", flush=True)

    # Stream live (stderr merged) so stages show up in `modal run` as they happen,
    # rather than dumping at the end. SIA prints generation/agent transitions; our
    # target agent + evaluate.py print [SIM]/[HARNESS]/[FOOTPRINT] markers.
    proc = subprocess.Popen(cmd, cwd=str(work), env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines: list[str] = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    rc = proc.wait()

    run_dir = work / "runs" / f"run_{run_id}"
    generations = []
    artifacts: dict[str, str] = {}
    CAP = 200_000

    def _grab(p: Path, rel: str) -> None:
        if p.exists():
            artifacts[rel] = p.read_text(errors="replace")[:CAP]

    if run_dir.exists():
        _grab(run_dir / "context.md", "context.md")
        gen_dirs = sorted(run_dir.glob("gen_*"))
        for gdir in gen_dirs:
            rj = gdir / "results.json"
            # The refined Verilog the agent submitted this generation (id -> RTL).
            submission: dict[str, str] = {}
            for vf in sorted((gdir / "submission").glob("*.v")):
                submission[vf.stem] = vf.read_text(errors="replace")[:CAP]
                _grab(vf, f"{gdir.name}/submission/{vf.name}")
            generations.append({
                "gen": gdir.name,
                "results": json.loads(rj.read_text()) if rj.exists() else None,
                "has_target_agent": (gdir / "target_agent.py").exists(),
                "submission": submission,
            })
            _grab(gdir / "target_agent.py", f"{gdir.name}/target_agent.py")
            _grab(gdir / "results.json", f"{gdir.name}/results.json")
            _grab(gdir / "agent_execution.json", f"{gdir.name}/agent_execution.json")
            _grab(gdir / "improvement.md", f"{gdir.name}/improvement.md")
        # Diff the harness the feedback agent evolved across the first two generations.
        if len(gen_dirs) >= 2:
            import difflib
            a, b = gen_dirs[0] / "target_agent.py", gen_dirs[1] / "target_agent.py"
            if a.exists() and b.exists():
                diff = difflib.unified_diff(
                    a.read_text().splitlines(), b.read_text().splitlines(),
                    f"{gen_dirs[0].name}/target_agent.py", f"{gen_dirs[1].name}/target_agent.py",
                    lineterm="")
                artifacts["target_agent_gen1_to_gen2.diff"] = "\n".join(diff)[:CAP]

    # Best generation = highest mean_reward; surface its refined RTL as the result.
    scored = [g for g in generations if g["results"]]
    best = max(scored, key=lambda g: g["results"].get("mean_reward", 0.0), default=None)

    artifacts["run_log_tail.txt"] = "".join(lines)[-20000:]
    return {
        "returncode": rc,
        "stdout_tail": "".join(lines)[-6000:],
        "generations": generations,
        "artifacts": artifacts,
        "best_gen": best["gen"] if best else None,
        "best_mean_reward": best["results"].get("mean_reward") if best else None,
        "best_rtl": best["submission"] if best else {},
    }


@app.function(image=sia_image, secrets=[modal.Secret.from_name("fireworks-api")], timeout=1800, cpu=2.0)
def seed_run_remote(target_model: str, n_candidates: int, temperature: float, max_repair: int) -> dict:
    """Run the seed harness + evaluate directly (no meta-agent) to demo live stage
    logging and validate the deployed-verifier grading path independent of SIA.
    """
    import os
    import subprocess
    from pathlib import Path

    subprocess.run(["uv", "pip", "install", "--system", "-e", REPO], check=True, capture_output=True)
    task = Path(TASK_DIR)
    gen = Path("/root/seed_gen")
    gen.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["COLOGIC_TARGET_MODEL"] = target_model
    env["COLOGIC_N_CANDIDATES"] = str(n_candidates)
    env["COLOGIC_TEMPERATURE"] = str(temperature)
    env["COLOGIC_MAX_REPAIR"] = str(max_repair)

    def _stream(cmd: list[str]) -> int:
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
        for line in p.stdout:
            print(line, end="", flush=True)
        return p.wait()

    print("[SEED] running the seed harness (no meta-agent) on the public designs ...\n", flush=True)
    agent_rc = _stream(["python", "-u", str(task / "reference/reference_target_agent.py"),
                        "--dataset_dir", str(task / "data/public"), "--working_dir", str(gen)])
    print("\n[SEED] scoring the submission with the immutable verifier ...\n", flush=True)
    eval_rc = _stream(["python", "-u", str(task / "data/public/evaluate.py"), "--gen-dir", str(gen)])

    rj = gen / "results.json"
    return {"agent_rc": agent_rc, "eval_rc": eval_rc,
            "results": json.loads(rj.read_text()) if rj.exists() else None}


def _patch_profile(path, model: str) -> None:
    data = json.loads(path.read_text())
    data["model"] = model
    path.write_text(json.dumps(data, indent=2) + "\n")


def _prepare_upload_task_dir(upload: dict, run_id: int):
    """Build a per-run SIA task dir whose public dataset IS the uploaded design.

    Copies the canonical task dir (task.md / evaluate.py / reference agent / profiles)
    and replaces data/public with a one-entry manifest pointing at the uploaded
    files (+ scaffold stimulus for clocked designs). The manifest schema is exactly
    what cologic.upload.task_from_manifest_entry consumes, so the agent + evaluate.py
    build the same Task they would for a registered design.

    `upload` keys: id, files {name: content}, stimulus?, top_module?, prompt?,
    n_vectors?, seed?.
    """
    import shutil
    import sys
    from pathlib import Path

    # sia_image copies the repo to REPO but doesn't put it on sys.path (cologic is
    # only pip-installed inside the per-generation venvs). The orchestrator needs
    # the shared dataset writer, so make cologic importable here.
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from cologic.upload import write_upload_dataset

    dst = Path(f"/root/task_upload_{run_id}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(TASK_DIR, dst)
    # Replace the baked-in benchmark dataset with the uploaded design (shared writer).
    write_upload_dataset(dst / "data" / "public", upload)
    return dst


@app.local_entrypoint()
def main(
    max_gen: int = 2,
    run_id: int = 1,
    target_model: str = "accounts/fireworks/models/kimi-k2p7-code",
    meta_model: str = "sonnet",  # Claude alias for the meta/feedback agent
    n_candidates: int = 4,
    temperature: float = 0.9,
    max_repair: int = 1,
    meta_max_turns: int = 60,
):
    """Run the SIA harness loop. SPENDS Fireworks tokens (meta + target x generations)."""
    r = sia_run_remote.remote(max_gen, run_id, target_model, meta_model,
                              n_candidates, temperature, max_repair, meta_max_turns)
    print(f"\nsia run rc={r['returncode']}\n")
    # Footprint across generations — "how the harness is improving the designs so far".
    print(f"{'generation':<10} {'mean_reward':>12} {'mean_area_impr':>15} {'equiv':>8}")
    print("-" * 50)
    for g in r["generations"]:
        res = g["results"] or {}
        ai = res.get("mean_area_improvement")
        ai_s = "n/a" if ai is None else f"{ai * 100:+.1f}%"
        eq = f"{res.get('n_equivalent', '?')}/{res.get('n_total', '?')}"
        print(f"{g['gen']:<10} {res.get('mean_reward', 0):>12.4f} {ai_s:>15} {eq:>8}")
    if r["returncode"] != 0:
        print(f"\n[SIA] exited rc={r['returncode']} — output tail:\n" + r["stdout_tail"][-2000:])

    # Capture the evidence locally under artifacts/.
    from pathlib import Path
    out_dir = Path("artifacts") / f"sia_run_{run_id}"
    for rel, content in (r.get("artifacts") or {}).items():
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    rows = "\n".join(
        f"| {g['gen']} | {(g['results'] or {}).get('mean_reward', 0):.4f} | "
        f"{((g['results'] or {}).get('mean_area_improvement') or 0) * 100:+.1f}% | "
        f"{(g['results'] or {}).get('n_equivalent', '?')}/{(g['results'] or {}).get('n_total', '?')} |"
        for g in r["generations"])
    (out_dir / "README.md").write_text(
        f"# SIA harness-lever run {run_id}\n\n"
        f"meta={meta_model} · target={target_model} · max_gen={max_gen} · "
        f"n_candidates={n_candidates}\n\n"
        f"Footprint per generation (official score from evaluate.py = deployed verifier):\n\n"
        f"| generation | mean_reward | mean_area_improvement | equivalent |\n"
        f"|---|---|---|---|\n{rows}\n\n"
        f"Artifacts: per-generation `target_agent.py` (the evolved harness), `results.json`, "
        f"`agent_execution.json`, `context.md`, and `target_agent_gen1_to_gen2.diff`.\n")
    print(f"\nwrote evidence to {out_dir}/ ({len(r.get('artifacts') or {})} files)")


@app.local_entrypoint()
def seed(
    target_model: str = "accounts/fireworks/models/kimi-k2p7-code",
    n_candidates: int = 2,
    temperature: float = 0.9,
    max_repair: int = 1,
):
    """Demo the harness + verifier + live stage logging WITHOUT the meta-agent.

    Streams [HARNESS] (sampling/repair), [SIM] (verifier triggered), [FOOTPRINT]
    (gate-count result), [EVAL]. Validates the deployed-grader path end to end.

      modal run scripts/modal_sia_run.py::seed
    """
    r = seed_run_remote.remote(target_model, n_candidates, temperature, max_repair)
    res = r["results"] or {}
    print(f"\n[SEED] agent_rc={r['agent_rc']} eval_rc={r['eval_rc']}")
    print(f"[FOOTPRINT] final: mean_area_improvement="
          f"{res.get('mean_area_improvement', 0) * 100:+.1f}% "
          f"equiv={res.get('n_equivalent', '?')}/{res.get('n_total', '?')} "
          f"mean_reward={res.get('mean_reward', 0):.3f}")


@app.local_entrypoint()
def validate_entry():
    """Cheap preflight (no LLM calls): modal run scripts/modal_sia_run.py::validate_entry"""
    import json as _json

    print(_json.dumps(validate.remote(), indent=2))
