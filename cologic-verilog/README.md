# Verilog Template (HUD v6)

A HUD v6 chip-design environment. The agent gets one Verilog/SystemVerilog task over an `ssh`
shell and is graded by hidden EDA flows. Three tracks share one module, `stream_arb_fifo`, a
two-lane ready/valid FIFO arbiter:

> edit the RTL, testbench, or proof → run the hidden flow → score against golden + mutants.

## Tasks

| Task | Track | What the agent does | Graded by |
|------|-------|---------------------|-----------|
| `stream-arb-fifo-repair` | RTL repair | fix a buggy FIFO arbiter | Verilator sim + Yosys synthesis/latch + lint |
| `stream-arb-fifo-cocotb-dv` | cocotb DV | write a testbench that catches mutant DUTs | golden pass + mutant kill + coverage |
| `stream-arb-fifo-formal` | formal | write SystemVerilog property checks | bounded SymbiYosys proofs + cover |

Each prompt states the contract the hidden grader checks. The image bundles the DV stack
(`cocotb`, `cocotb-bus`, `cocotb-coverage`, `pyuvm`, `hypothesis`) and the formal toolchain
(`sby`, Yosys, Z3).

**Isolation (uid wall).** The env serves and grades as root, but the agent's shell runs as an
unprivileged `agent` uid via `setpriv`, so it can't read the root-owned answer key under
`/donotaccess`. bwrap (v6's usual shell jail) can't create namespaces in platform containers, so
the uid wall is what protects the key.

## Setup

```sh
uv sync                            # hud v6 + the cocotb DV stack
hud set HUD_API_KEY=your-key-here  # CLI auth, get one at hud.ai/project/api-keys
```

Local runs need `verilator`, `yosys`, `sby`, and `z3` on `PATH`. All four ship in
[OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases/latest): extract it and
add its `bin/` to `PATH` (on macOS, clear quarantine first: `xattr -dr com.apple.quarantine <dir>`).

## Run

```sh
# local
hud eval tasks.py claude --task-ids stream-arb-fifo-repair --group 1 -y

# deploy once, then run hosted
hud deploy .
hud sync tasks <taskset-name> --yes
hud eval tasks.py claude --runtime hud --full
```

## Verify the graders

Each track has a calibration script that runs its grader against known submissions and checks the
reward:

```sh
uv run python tasks/stream_arb_fifo_repair/scripts/check_calibration.py      # buggy 0.0, golden 1.0, latch-left 0.7
uv run python tasks/stream_arb_fifo_cocotb_dv/scripts/check_calibration.py   # starter 0.25, reference 1.0
uv run python tasks/stream_arb_fifo_formal/scripts/check_calibration.py      # starter 0.35, reference 1.0
```

## Layout

Hidden grader files and baselines live under root-owned `/donotaccess/<task_id>`; at setup, only
the selected task's agent-facing files land in the workspace `/workdir`. `donotaccess/` is checked
in so the grader structure is inspectable. Third-party HDL is vendored per task under
`vendor/basejump_stl` (Solderpad license; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)).

## Documentation

See the [full docs](https://docs.hud.ai) for tasks, evaluation, and scaling.
