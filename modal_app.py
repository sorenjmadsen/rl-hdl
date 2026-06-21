"""Modal app: parallel Verilator grading + the baseline eval entrypoint.

Grading runs in Modal containers (one Verilator build, fanned out with .map),
so rollouts/sec scales with container count rather than local cores. Inference
(Fireworks) runs locally in the entrypoint and is just concurrent HTTP.

Usage:
  modal run modal_app.py --selftest            # no API key; goldens -> pass@1 = 1.0
  modal run modal_app.py --split heldout --n 5 # zero-shot baseline (needs FIREWORKS_API_KEY)
  modal run modal_app.py --split gradient --n 1
  modal run modal_app.py --split train --n 1
"""

from __future__ import annotations

from pathlib import Path

import modal

# FastAPI resolves route annotations against this module's globals. Under
# `from __future__ import annotations` the `list[UploadFile]` hint on /optimize is
# a string, so UploadFile must be importable at module scope (not just inside
# web()). Guarded so local imports without fastapi still succeed — the web image
# always ships it.
try:
    from fastapi import UploadFile
except ModuleNotFoundError:
    UploadFile = None

VERILATOR_TAG = "v5.038"

# Open standard-cell library for real-area (um^2) measurement. Single self-contained
# .lib; swappable to Sky130 by changing the URL + path (the grader only reads the
# RLHDL_LIBERTY env var). Real area is OBSERVE-ONLY today — the reward still ranks on
# technology-independent cell count — so a fetch failure cannot affect grading.
LIBERTY_URL = (
    "https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/"
    "master/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib"
)
LIBERTY_PATH = "/opt/pdk/NangateOpenCellLibrary_typical.lib"

# Silicon toolchain (Verilator + Yosys), no local source yet so we can branch it.
_toolchain = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git", "make", "g++", "autoconf", "flex", "bison",
        "help2man", "libfl-dev", "ccache", "perl",
        # Yosys for the PPA (gate-count) stage; only runs behind a passing
        # equivalence check. Equivalence itself uses the Verilator built below.
        "yosys",
        # curl + certs to fetch the liberty library below.
        "curl", "ca-certificates",
    )
    .run_commands(
        f"git clone --depth 1 --branch {VERILATOR_TAG} "
        "https://github.com/verilator/verilator.git /tmp/verilator",
        "cd /tmp/verilator && autoconf && ./configure && "
        "make -j$(nproc) && make install && rm -rf /tmp/verilator",
        f"mkdir -p /opt/pdk && curl -fsSL {LIBERTY_URL} -o {LIBERTY_PATH}",
    )
    .env({"RLHDL_LIBERTY": LIBERTY_PATH})
)

grader_image = _toolchain.add_local_python_source("cologic")

# The harness runs sampling (Fireworks) AND grading (Verilator+Yosys) in one
# container, so it needs the toolchain + the OpenAI client + both packages.
harness_image = (
    _toolchain
    .pip_install("openai>=1.0")
    .add_local_python_source("cologic", "harness")
)

# Lightweight image for inference — just the OpenAI-compatible client. The
# Fireworks key arrives via the `fireworks-api` Modal Secret, so sampling has no
# dependency on the caller's local Python env.
inference_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai>=1.0")
    .add_local_python_source("cologic")
)

# The public web API (FastAPI/ASGI). It only builds Tasks from uploads and
# spawns/polls the optimization functions, so it stays light — no toolchain, no
# Fireworks client. Verilator/Yosys/Fireworks live in the worker functions it calls.
web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]")
    .add_local_python_source("cologic")
)

# Default Fireworks policy for the upload flow (matches the flywheel_run entrypoint).
DEFAULT_MODEL = "accounts/fireworks/models/kimi-k2p7-code"

app = modal.App("rl-hdl")

# grade().info keys surfaced into the JSON dumps + demo tables. Cell count drives
# the reward today; the real-area (um^2) keys ride alongside as observe-only. When
# we flip the reward to real area, this stays the single list to read from.
_SURFACED_INFO_KEYS = (
    "stage", "equivalent", "ref_cells", "cand_cells", "area_improvement",
    "ref_area_um2", "cand_area_um2", "area_um2_improvement",
)


def _pct(x) -> str:
    """Signed percentage for an improvement fraction, blank if unmeasured."""
    return "" if x is None else f"{x * 100:+.1f}%"


def _area(x) -> str:
    """Compact um^2 area, blank if no liberty library was configured."""
    return "" if x is None else f"{x:.0f}"


@app.function(image=grader_image, timeout=180)
def grade_remote(completion: str, task) -> dict:
    """Grade one (completion, task) in a container. Task pickles via cologic."""
    from cologic.verifier import grade

    r = grade(completion, task)
    return {"reward": r.reward, "info": r.info, "task_id": task.task_id}


@app.function(image=grader_image, timeout=300)
def grade_opt_remote(candidate_rtl: str, task) -> dict:
    """Grade one optimization candidate (gate-then-climb, incl. Yosys PPA)."""
    from cologic.grader import grade

    r = grade(candidate_rtl, task)
    return {"reward": r.reward, "info": r.info, "task_id": task.task_id}


@app.function(image=grader_image, timeout=300)
def synth_cells_remote(rtl: str, top_module: str) -> int:
    """Diagnostic: Yosys post-synth cell count for a raw RTL string (no equivalence).

    A task-curation tool — quantify a design's *headroom* by synthesizing a bloated
    baseline and its tight equivalent and comparing cells.
    """
    from cologic.grader.ppa import synth_cells

    return synth_cells(rtl, top_module).cells


@app.function(image=harness_image, secrets=[modal.Secret.from_name("fireworks-api")], timeout=1200)
def optimize_remote(task, model: str, n_candidates: int, temperature: float,
                    max_repair_rounds: int) -> dict:
    """Run the MAGE-repurposed harness on one design, in one container.

    Sampling (Fireworks) and grading (Verilator equivalence + Yosys PPA) happen
    here together, so the returned numbers are end-to-end real. Returns a compact
    summary (no full RTL logs) plus the best candidate's RTL.
    """
    import time

    from harness import HarnessConfig, default_model_fn, optimize

    # Warm the deployment through scale-from-zero (Fireworks 503s for a few minutes
    # when cold; the client's own retries don't span that). One-off demo concern,
    # kept out of the SIA-evolved scaffold.
    for _ in range(40):
        try:
            default_model_fn([{"role": "user", "content": "ping"}], model=model,
                             temperature=0.0, max_tokens=1)
            break
        except Exception as e:  # noqa: BLE001
            if "scal" in str(e).lower() or "503" in str(e):
                time.sleep(15)
                continue
            raise

    def model_fn(messages, *, temperature, max_tokens):
        return default_model_fn(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    res = optimize(task, model_fn=model_fn, config=HarnessConfig(
        n_candidates=n_candidates, temperature=temperature, max_repair_rounds=max_repair_rounds,
    ))
    pool = [
        {"origin": c.origin, "reward": round(c.reward, 4),
         **{k: c.info.get(k) for k in _SURFACED_INFO_KEYS}}
        for c in res.pool
    ]
    return {
        "task_id": task.task_id,
        "best": {"origin": res.best.origin, "reward": round(res.best.reward, 4),
                 "info": {k: res.best.info.get(k) for k in _SURFACED_INFO_KEYS},
                 "rtl": res.best.rtl},
        "baseline_reward": round(res.baseline_reward, 4),
        "n_equivalent": res.n_equivalent,
        "improved": res.improved,
        "pool": pool,
    }


@app.function(image=harness_image, secrets=[modal.Secret.from_name("fireworks-api")], timeout=3600)
def flywheel_remote(task, model: str, n_candidates: int, temperature: float,
                    max_repair_rounds: int, max_generations: int, patience: int,
                    max_tokens: int = 4096) -> dict:
    """Run the single-design flywheel on one design until its gate count plateaus.

    Sampling (Fireworks) + equivalence (Verilator) + PPA (Yosys) all in-container,
    so the gate-count curve is real. Returns the per-generation trajectory.
    """
    import time

    from harness import FlywheelConfig, HarnessConfig, default_model_fn, run_flywheel

    for _ in range(40):  # warm the deployment through scale-from-zero
        try:
            default_model_fn([{"role": "user", "content": "ping"}], model=model,
                             temperature=0.0, max_tokens=1)
            break
        except Exception as e:  # noqa: BLE001
            if "scal" in str(e).lower() or "503" in str(e):
                time.sleep(15)
                continue
            raise

    def model_fn(messages, *, temperature, max_tokens):
        return default_model_fn(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    res = run_flywheel(task, model_fn=model_fn, config=FlywheelConfig(
        max_generations=max_generations, patience=patience,
        harness=HarnessConfig(n_candidates=n_candidates, temperature=temperature,
                              max_repair_rounds=max_repair_rounds, max_tokens=max_tokens),
    ))
    return {
        "task_id": res.task_id,
        "baseline_cells": res.baseline_cells,
        "best_cells": res.best_cells,
        "total_improvement": res.total_improvement,
        "baseline_area_um2": res.baseline_area_um2,
        "best_area_um2": res.best_area_um2,
        "total_area_um2_improvement": res.total_area_um2_improvement,
        "plateaued": res.plateaued,
        "history": [{"gen": g.gen, "cells": g.cells, "reward": round(g.reward, 4),
                     "equivalent": g.equivalent, "improved": g.improved,
                     "area_um2": g.area_um2} for g in res.history],
        "best_rtl": res.best_rtl,
    }


@app.function(image=grader_image, timeout=120)
def validate_upload_remote(task) -> dict:
    """Cheap pre-flight: grade the uploaded reference against ITSELF.

    A well-formed interface + testbench must grade the design equivalent to itself
    over a non-empty number of comparisons. This catches a malformed scaffold
    stimulus or a mis-parsed interface in ~one Verilator build, before we spend a
    full (minutes-long) optimization loop on it.
    """
    from cologic.grader import grade

    r = grade(task.reference_rtl, task)
    return {
        "ok": bool(r.info.get("equivalent")) and (r.info.get("eq_total") or 0) > 0,
        "stage": r.info.get("stage"),
        "eq_total": r.info.get("eq_total"),
        "baseline_cells": r.info.get("cand_cells") or r.info.get("ref_cells"),
        "log": (r.info.get("log") or "")[-2000:],
    }


@app.function(
    image=web_image,
    secrets=[modal.Secret.from_name("rlhdl-web")],  # provides RLHDL_WEB_TOKEN
    timeout=300,
    # Cold-starts on first hit; add min_containers=1 to keep it warm (costs $).
)
@modal.asgi_app()
def web():
    """Public optimizer API for the Vercel frontend.

    POST /optimize  (multipart): files[] (.v), prompt, optional stimulus +
                    top_module + knobs -> {job_id}. Spawns the flywheel async.
    GET  /jobs/{id}: poll -> {status: running|done|error, result?}.

    Auth: a shared token in the `X-RLHDL-Token` header, compared to the
    RLHDL_WEB_TOKEN secret. Create it once with:
        modal secret create rlhdl-web RLHDL_WEB_TOKEN=<pick-a-token>
    If the secret is empty/unset the API runs open (dev only).
    """
    import os

    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware

    api = FastAPI(title="rl-hdl optimizer")
    # No custom domain yet; allow any origin (the shared token is the gate).
    api.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    token = os.environ.get("RLHDL_WEB_TOKEN") or ""

    def check_auth(supplied: str | None) -> None:
        if token and supplied != token:
            raise HTTPException(status_code=401, detail="missing or invalid X-RLHDL-Token")

    @api.post("/optimize")
    async def optimize(
        prompt: str = Form(...),
        stimulus: str | None = Form(None),
        top_module: str | None = Form(None),
        mode: str = Form("sia"),                  # "sia" (scaffold evolution) | "harness"
        n_candidates: int = Form(4),
        temperature: float = Form(0.9),
        max_repair_rounds: int = Form(1),
        max_generations: int = Form(2),           # SIA generations are expensive — keep low
        patience: int = Form(3),                  # harness mode only
        meta_model: str = Form("sonnet"),         # SIA meta/feedback agent (Claude)
        meta_max_turns: int = Form(60),           # SIA mode only
        max_tokens: int = Form(4096),             # per-sample generation budget
        n_vectors: int = Form(256),               # equivalence vectors (combinational designs)
        model: str = Form(DEFAULT_MODEL),         # target policy (Fireworks)
        files: list[UploadFile] = File(...),
        x_rlhdl_token: str | None = Header(default=None),
    ):
        check_auth(x_rlhdl_token)
        from cologic.upload import task_from_upload

        sources = {f.filename: (await f.read()).decode("utf-8", "replace") for f in files}
        try:
            task = task_from_upload(
                sources, prompt=prompt, stimulus=stimulus, top_module=top_module,
                n_vectors=n_vectors,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Pre-flight (both modes): a malformed interface/testbench fails fast here,
        # before a long, billable optimization run.
        v = validate_upload_remote.remote(task)
        if not v["ok"]:
            raise HTTPException(
                status_code=400,
                detail=(f"pre-flight failed (stage={v['stage']}): the interface/testbench "
                        f"does not grade the design equivalent to itself.\n{v['log'][-800:]}"),
            )

        if mode == "sia":
            # Full SIA loop (meta agent evolves the scaffold) — a separate app.
            import time

            upload = {
                "id": task.top_module,
                "files": sources,
                "stimulus": stimulus,
                "top_module": top_module or task.top_module,
                "prompt": prompt,
                "n_vectors": n_vectors,
                "seed": task.seed,
            }
            sia = modal.Function.from_name("rl-hdl-sia", "sia_run_remote")
            call = sia.spawn(
                max_generations, int(time.time()), model, meta_model,
                n_candidates, temperature, max_repair_rounds, meta_max_turns, upload,
                max_tokens,
            )
        else:
            call = flywheel_remote.spawn(
                task, model, n_candidates, temperature,
                max_repair_rounds, max_generations, patience, max_tokens,
            )

        return {
            "job_id": call.object_id,
            "mode": mode,
            "top_module": task.top_module,
            "clocked": task.clocked,
            "baseline_cells": v["baseline_cells"],
        }

    @api.get("/jobs/{job_id}")
    async def job(job_id: str, x_rlhdl_token: str | None = Header(default=None)):
        check_auth(x_rlhdl_token)
        fc = modal.FunctionCall.from_id(job_id)
        try:
            return {"status": "done", "result": fc.get(timeout=0)}
        except TimeoutError:
            return {"status": "running"}
        except Exception as e:  # noqa: BLE001 — surface a remote failure as JSON, not 500
            return {"status": "error", "error": str(e)}

    return api


@app.function(image=harness_image, secrets=[modal.Secret.from_name("fireworks-api")], timeout=3600)
def measure_remote(task, model: str, n_candidates: int, temperature: float,
                   max_repair_rounds: int, max_generations: int, patience: int) -> dict:
    """The headline gap: baseline vs zero-shot vs full-loop on one design.

    Same Fireworks policy and same immutable grader (Verilator equivalence + Yosys
    PPA) for every arm, so `gap_cells` is exactly what the search/repair machinery
    bought beyond a single zero-shot sample. The design's optimum is never supplied.
    """
    import time

    from harness import FlywheelConfig, HarnessConfig, default_model_fn, format_gap, measure_gap

    for _ in range(40):  # warm the deployment through scale-from-zero
        try:
            default_model_fn([{"role": "user", "content": "ping"}], model=model,
                             temperature=0.0, max_tokens=1)
            break
        except Exception as e:  # noqa: BLE001
            if "scal" in str(e).lower() or "503" in str(e):
                time.sleep(15)
                continue
            raise

    def model_fn(messages, *, temperature, max_tokens):
        return default_model_fn(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    res = measure_gap(
        task, model_fn=model_fn,
        loop_config=FlywheelConfig(
            max_generations=max_generations, patience=patience,
            harness=HarnessConfig(n_candidates=n_candidates, temperature=temperature,
                                  max_repair_rounds=max_repair_rounds),
        ),
    )

    def arm(a) -> dict:
        return {"name": a.name, "cells": a.cells, "reward": round(a.reward, 4),
                "equivalent": a.equivalent, "rtl": a.rtl, "area_um2": a.area_um2}

    return {
        "task_id": res.task_id,
        "baseline_cells": res.baseline_cells,
        "baseline_area_um2": res.baseline_area_um2,
        "zero_shot": arm(res.zero_shot),
        "loop": arm(res.loop),
        "gap_cells": res.gap_cells,
        "loop_beats_zero_shot": res.loop_beats_zero_shot,
        "table": format_gap(res),
    }


@app.function(image=inference_image, secrets=[modal.Secret.from_name("fireworks-api")])
def list_models(substr: str = "") -> list[str]:
    """Return Fireworks model ids visible to this account (optionally filtered)."""
    import os

    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["FIREWORKS_API_KEY"],
        base_url=os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
    )
    ids = [m.id for m in client.models.list().data]
    return sorted(i for i in ids if substr.lower() in i.lower())


@app.function(image=inference_image, secrets=[modal.Secret.from_name("fireworks-api")], timeout=120)
def probe_model(model: str) -> dict:
    """Return whether a Fireworks chat model is callable for this account."""
    import os

    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["FIREWORKS_API_KEY"],
        base_url=os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
        max_retries=1,
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
            temperature=0,
        )
        return {"model": model, "ok": True, "text": resp.choices[0].message.content or ""}
    except Exception as exc:
        return {"model": model, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


@app.function(image=inference_image, secrets=[modal.Secret.from_name("fireworks-api")], timeout=900)
def sample_remote(task, model: str, max_tokens: int | None, temperature: float) -> dict:
    """One completion from Fireworks (budget auto-grows on truncation).

    Mapped per (task, sample) so every completion is an independent Modal input —
    maximum parallelism, and no single container runs n calls in series (which
    could blow the timeout). Returns {text, finish_reason, budget}.
    """
    from cologic.inference import sample_until_complete

    text, finish, budget = sample_until_complete(
        task, model=model, temperature=temperature, max_tokens=max_tokens
    )
    return {"text": text, "finish_reason": finish, "budget": budget}


@app.local_entrypoint()
def main(
    split: str = "heldout",
    n: int = 1,
    selftest: bool = False,
    out: str = "baseline.json",
    dump: str = "",
    max_tokens: int = 0,
):
    from collections import Counter

    from cologic.eval import aggregate

    if split == "verilogeval":
        from cologic.datasets.verilogeval import load as load_verilogeval

        tasks = load_verilogeval()
    else:
        from cologic.tasks import GRADIENT_TASKS, HELDOUT_TASKS, SEED_TASKS, TRAIN_TASKS

        tasks = {
            "heldout": HELDOUT_TASKS,
            "train": TRAIN_TASKS,
            "gradient": GRADIENT_TASKS,
            "rft": TRAIN_TASKS + GRADIENT_TASKS,
            "all": SEED_TASKS,
        }[split]

    if selftest:
        # Feed each task its own golden reference: a green end-to-end check of the
        # Modal grader with no model / API key required (expect pass@1 = 1.0).
        samples = [(t, t.reference_rtl, "selftest") for t in tasks]
        model = "selftest-golden"
    else:
        from cologic.inference import model_id

        model = model_id()
        override = max_tokens or None  # 0 sentinel -> per-task/env resolution + auto-grow
        temperature = 0.0 if n == 1 else 0.7  # greedy for a stable n=1 read, else sample
        budget_desc = f"override={override}" if override else "per-task/auto-grow"
        jobs = [t for t in tasks for _ in range(n)]  # one Modal input per completion
        print(f"sampling n={n} ({len(jobs)} completions) from {model} "
              f"(max_tokens={budget_desc}, temp={temperature}) for {len(tasks)} {split} tasks (in Modal) ...")
        dicts = list(sample_remote.map(
            jobs, [model] * len(jobs), [override] * len(jobs), [temperature] * len(jobs)
        ))
        budgets = [d["budget"] for d in dicts]
        print(f"token budgets used: min={min(budgets)} max={max(budgets)} (auto-grew on truncation)")
        samples = [(t, d["text"], d["finish_reason"]) for t, d in zip(jobs, dicts)]

    pairs = [(t, txt) for t, txt, _ in samples]
    results = list(grade_remote.map([c for _, c in pairs], [t for t, _ in pairs]))

    report = aggregate(pairs, results, model=model)
    print("\n" + report.table() + "\n")
    print("finish_reason:", dict(Counter(f for _, _, f in samples)))
    Path(out).write_text(report.to_json())
    print(f"wrote {out}")

    if dump:
        import json

        with open(dump, "w") as fh:
            for (t, txt, finish), res in zip(samples, results):
                fh.write(json.dumps({
                    "task_id": t.task_id,
                    "finish_reason": finish,
                    "reward": res["reward"],
                    "stage": res["info"].get("stage"),
                    "completion": txt,
                }) + "\n")
        print(f"wrote {dump} ({len(samples)} records)")


@app.local_entrypoint()
def floor():
    """§9 floor: grade the baseline + a good and a broken rewrite of mul8.

    Proves the immutable grader end to end with real Yosys area numbers:
      baseline -> equivalent, 0 area win        (it IS the reference)
      good     -> equivalent, area win > 0       (the optimization to discover)
      broken   -> not equivalent, no PPA credit  (gate catches the break)

    Usage:  modal run modal_app.py::floor
    """
    from cologic.designs import MUL8_BASELINE, MUL8_BROKEN, MUL8_GOOD, mul8

    cands = [("baseline", MUL8_BASELINE), ("good (a*b)", MUL8_GOOD), ("broken", MUL8_BROKEN)]
    results = list(grade_opt_remote.map([c for _, c in cands], [mul8] * len(cands)))

    print(f"\nfloor design: {mul8.task_id} ({mul8.top_module})\n")
    print(f"{'candidate':<14} {'reward':>7}  {'stage':<18} {'equiv':>5} {'ref':>5} {'cand':>5} "
          f"{'win':>7} {'um²':>8} {'um²win':>7}")
    print("-" * 86)
    for (name, _), r in zip(cands, results):
        i = r["info"]
        win = _pct(i.get("area_improvement"))
        ref = "" if i["ref_cells"] is None else i["ref_cells"]
        cand = "" if i["cand_cells"] is None else i["cand_cells"]
        print(f"{name:<14} {r['reward']:>7.3f}  {i['stage']:<18} {str(i['equivalent']):>5} "
              f"{str(ref):>5} {str(cand):>5} {win:>7} "
              f"{_area(i.get('cand_area_um2')):>8} {_pct(i.get('area_um2_improvement')):>7}")
    print()


@app.local_entrypoint()
def harness_run(
    design: str = "mul8",
    model: str = "accounts/fireworks/models/kimi-k2p7-code",
    n: int = 6,
    temperature: float = 0.9,
    repair: int = 2,
):
    """Live demo: run the MAGE harness on a real design with the Fireworks policy.

    Sampling + Verilator equivalence + Yosys PPA all run in one Modal container.
    The headline is whether the policy found a provably-equivalent, smaller design.

    Usage:  modal run modal_app.py::harness_run            # mul8, default policy
            modal run modal_app.py::harness_run --n 10 --temperature 1.0
    """
    from cologic.designs import BY_ID

    task = BY_ID[f"opt_{design}"] if f"opt_{design}" in BY_ID else BY_ID[design]
    print(f"\nharness on {task.task_id} ({task.top_module}) | model={model} "
          f"| n={n} temp={temperature} repair={repair}\n")

    r = optimize_remote.remote(task, model, n, temperature, repair)

    print(f"{'candidate':<34} {'reward':>7}  {'stage':<18} {'equiv':>5} {'ref':>5} {'cand':>5} "
          f"{'win':>7} {'um²':>8} {'um²win':>7}")
    print("-" * 108)
    for c in r["pool"]:
        win = _pct(c.get("area_improvement"))
        ref = "" if c["ref_cells"] is None else c["ref_cells"]
        cand = "" if c["cand_cells"] is None else c["cand_cells"]
        print(f"{c['origin']:<34} {c['reward']:>7.3f}  {str(c['stage']):<18} "
              f"{str(c['equivalent']):>5} {str(ref):>5} {str(cand):>5} {win:>7} "
              f"{_area(c.get('cand_area_um2')):>8} {_pct(c.get('area_um2_improvement')):>7}")

    b = r["best"]
    print(f"\nbest: {b['origin']}  reward={b['reward']}  "
          f"equivalent={b['info'].get('equivalent')}  "
          f"area_improvement={b['info'].get('area_improvement')}  "
          f"area_um2_improvement={b['info'].get('area_um2_improvement')}")
    print(f"baseline_reward={r['baseline_reward']}  n_equivalent={r['n_equivalent']}/"
          f"{len(r['pool'])}  improved={r['improved']}")
    if r["improved"]:
        print("\n--- winning RTL ---\n" + b["rtl"])
    print()


@app.local_entrypoint()
def flywheel_run(
    design: str = "mul8",
    model: str = "accounts/fireworks/models/kimi-k2p7-code",
    n: int = 6,
    temperature: float = 0.9,
    repair: int = 2,
    gens: int = 8,
    patience: int = 3,
):
    """Spin up the flywheel on ONE design and watch its gate count fall until it plateaus.

    Usage:  modal run modal_app.py::flywheel_run --design mul8
            modal run modal_app.py::flywheel_run --design popcount8 --gens 12 --patience 4
    """
    from cologic.designs import BY_ID

    task = BY_ID[f"opt_{design}"] if f"opt_{design}" in BY_ID else BY_ID[design]
    print(f"\nflywheel on {task.task_id} ({task.top_module}) | model={model} "
          f"| n={n} temp={temperature} repair={repair} gens={gens} patience={patience}\n")

    r = flywheel_remote.remote(task, model, n, temperature, repair, gens, patience)

    print(f"{'gen':>3} {'cells':>6} {'um²':>8} {'reward':>7} {'equiv':>6} {'improved':>9}")
    print("-" * 48)
    for h in r["history"]:
        cells = "" if h["cells"] is None else h["cells"]
        print(f"{h['gen']:>3} {str(cells):>6} {_area(h.get('area_um2')):>8} {h['reward']:>7.3f} "
              f"{str(h['equivalent']):>6} {str(h['improved']):>9}")

    imp = r["total_improvement"]
    imp_s = "n/a" if imp is None else f"{imp * 100:+.1f}%"
    um2_imp = r.get("total_area_um2_improvement")
    um2_s = "n/a" if um2_imp is None else f"{um2_imp * 100:+.1f}%"
    print(f"\nbaseline={r['baseline_cells']} cells -> best={r['best_cells']} cells ({imp_s})"
          f"  |  area {_area(r.get('baseline_area_um2'))} -> {_area(r.get('best_area_um2'))} um² ({um2_s})"
          f"  plateaued={r['plateaued']}")
    print("\n--- best RTL ---\n" + r["best_rtl"] + "\n")


@app.local_entrypoint()
def measure_run(
    design: str = "tpu_matmul2x2",
    model: str = "accounts/fireworks/models/kimi-k2p7-code",
    n: int = 8,
    temperature: float = 0.9,
    repair: int = 2,
    gens: int = 8,
    patience: int = 3,
):
    """Headline experiment: baseline vs zero-shot vs full-loop on a REAL design.

    Defaults to `tpu_matmul2x2` — the real `tt_um_tpu` 2x2 matmul accelerator, whose
    optimum we did not author. The number that matters is `gap_cells`: cells the
    loop saved beyond a single zero-shot sample, with Yosys as the only judge.

    Usage:  modal run modal_app.py::measure_run
            modal run modal_app.py::measure_run --design share_mul --gens 6
    """
    from cologic.designs import BY_ID, CLOCKED_OPT_TASKS

    lookup = dict(BY_ID)
    lookup.update({t.task_id: t for t in CLOCKED_OPT_TASKS})
    lookup.update({t.task_id.removeprefix("opt_"): t for t in lookup.values()})
    task = lookup.get(f"opt_{design}") or lookup.get(design)
    if task is None:
        raise SystemExit(f"unknown design {design!r}; known: {sorted(lookup)}")

    print(f"\nmeasure on {task.task_id} ({task.top_module}) | model={model} "
          f"| n={n} temp={temperature} repair={repair} gens={gens} patience={patience}\n")

    r = measure_remote.remote(task, model, n, temperature, repair, gens, patience)
    print(r["table"])
    if r["loop_beats_zero_shot"]:
        print("--- loop's winning RTL (beyond zero-shot) ---\n" + r["loop"]["rtl"] + "\n")


@app.local_entrypoint()
def headroom():
    """Probe which design patterns retain post-synth headroom (task-curation spike).

    Each pair is a bloated baseline + a hand-written tight EQUIVALENT. A large
    baseline->tight cell gap means real headroom an optimizer could capture even
    after full Yosys synth. Usage:  modal run modal_app.py::headroom
    """
    # (name, top, baseline_rtl, tight_rtl)  — same function, different structure.
    probes = [
        # Combinational resource sharing under a mutually-exclusive select: the
        # baseline instantiates two multipliers; the tight form shares one and
        # muxes the operands. Yosys `share` is NOT in the default synth recipe.
        ("share_mul", "share_mul",
         "module share_mul(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d, input s, output [15:0] y);\n"
         "  assign y = s ? (a * b) : (c * d);\nendmodule\n",
         "module share_mul(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d, input s, output [15:0] y);\n"
         "  assign y = (s ? a : c) * (s ? b : d);\nendmodule\n"),
        # Same idea with adders (smaller operator -> smaller gap).
        ("share_add", "share_add",
         "module share_add(input [15:0] a, input [15:0] b, input [15:0] c, input [15:0] d, input s, output [15:0] y);\n"
         "  assign y = s ? (a + b) : (c + d);\nendmodule\n",
         "module share_add(input [15:0] a, input [15:0] b, input [15:0] c, input [15:0] d, input s, output [15:0] y);\n"
         "  assign y = (s ? a : c) + (s ? b : d);\nendmodule\n"),
        # Control: redundant duplicated combinational expr (abc should kill it -> ~0 gap).
        ("redundant", "redundant",
         "module redundant(input [7:0] a, input [7:0] b, output [7:0] y);\n"
         "  assign y = (a + b) + (a + b) - (a + b);\nendmodule\n",
         "module redundant(input [7:0] a, input [7:0] b, output [7:0] y);\n"
         "  assign y = a + b;\nendmodule\n"),
    ]
    names = [p[0] for p in probes]
    base = list(synth_cells_remote.map([p[2] for p in probes], [p[1] for p in probes]))
    tight = list(synth_cells_remote.map([p[3] for p in probes], [p[1] for p in probes]))

    print(f"\n{'design':<12} {'baseline':>9} {'tight':>7} {'savings':>9}")
    print("-" * 42)
    for name, b, t in zip(names, base, tight):
        save = f"{(b - t) / b * 100:+.1f}%" if b else "n/a"
        print(f"{name:<12} {b:>9} {t:>7} {save:>9}")
    print()


@app.local_entrypoint()
def models(substr: str = ""):
    """List Fireworks models available to the account, e.g. --substr coder."""
    ids = list_models.remote(substr)
    print(f"\n{len(ids)} models" + (f" matching {substr!r}" if substr else "") + ":")
    for i in ids:
        print(f"  {i}")
    print()


@app.local_entrypoint()
def probe(models_csv: str):
    """Probe comma-separated Fireworks model ids for chat inference access."""
    model_ids = [m.strip() for m in models_csv.split(",") if m.strip()]
    for result in probe_model.map(model_ids):
        print(result)


@app.local_entrypoint()
def bench(total: int = 64):
    """Measure grading throughput (rollouts/sec) through the parallel grader.

    Grades golden references (correct, so they exercise the full compile+sim path)
    fanned out with .map across autoscaled containers.
    """
    import time

    from cologic.tasks import SEED_TASKS

    goldens = [(t, t.reference_rtl) for t in SEED_TASKS]
    pairs = [goldens[i % len(goldens)] for i in range(total)]
    comps = [c for _, c in pairs]
    tks = [t for t, _ in pairs]

    t0 = time.time()
    results = list(grade_remote.map(comps, tks))
    dt = time.time() - t0

    ok = sum(r["reward"] == 1.0 for r in results)
    print(f"\ngraded {len(results)} designs in {dt:.1f}s "
          f"({len(results) / dt:.1f} grades/sec), {ok}/{len(results)} == 1.0\n")
