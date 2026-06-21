"""verilog-template: HUD v6 chip-design environment.

Three tracks on one module (``stream_arb_fifo``): RTL repair, cocotb DV, and formal proofs.
Isolation (uid wall): the env serves and grades as root, but every agent shell command is
demoted to the unprivileged ``agent`` uid via ``setpriv`` (see ``_AgentWorkspace``), so the
agent can't read the root:700 answer key at ``/donotaccess/<id>`` while the grader can.
"""

# NOTE: this file deliberately omits ``from __future__ import annotations``. Do NOT add it
# back: under it, an @env.template parameter typed with Literal/Optional/an alias/a Pydantic
# model crashes at deploy/start (the server runs ``TypeAdapter`` on a string forward-ref ->
# PydanticUserError, surfaced as ``-32000``). Without it, annotations resolve to real objects
# and any param type works. Known SDK bug, leave the future-import out.
import os
import sys

from hud import Environment
from hud.environment import Workspace

from grader import evaluate_task
from scenario_helpers import WORKSPACE_ROOT, setup_task
from task_catalog import TASK_SPECS_BY_ID

AGENT_UID = int(os.environ.get("AGENT_UID", "1000"))
AGENT_GID = int(os.environ.get("AGENT_GID", "1000"))


class _AgentWorkspace(Workspace):
    """A Workspace whose interactive shell runs as the unprivileged ``agent`` uid.

    The env serves as root so the grader can read the root:700 answer key, but every agent
    command is wrapped in ``setpriv --reuid agent`` so the agent's shell cannot. This
    replaces v5's preexec demotion now that bwrap (the v6 jail) can't run in a container.
    No-op when not running as root (e.g. local macOS dev), where the shell already has no
    elevated access.

    ``shell_argv`` is a public Workspace method (the SDK labels its argv builders public)
    but is not listed in the v6 docs, so we pin the SDK commit: an upstream signature change
    must surface as a load error here, never as a silently bypassed uid wall.
    """

    def shell_argv(self, command=None, *, cwd=None, env=None):
        argv = super().shell_argv(command, cwd=cwd, env=env)
        if sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() == 0:
            argv = [
                "setpriv",
                "--reuid", str(AGENT_UID),
                "--regid", str(AGENT_GID),
                "--clear-groups",
                "--",
                *argv,
            ]
        return argv


# The env name MUST be a string literal: `hud deploy` resolves it by statically parsing
# this call, so a variable (env-var lookup) fails with "constructed without an explicit name".
env = Environment(name="verilog-template-v6")

# network=False mirrors v5's `--network none` air-gap (enforced by bwrap where available;
# on the platform, rely on a container-level network policy). HOME points at the agent's
# home so tools that write there don't hit the root-owned /root.
_ws = _AgentWorkspace(
    WORKSPACE_ROOT,
    network=False,
    env={"HOME": "/home/agent", "USER": "agent", "LOGNAME": "agent"},
)


@env.initialize
async def _up() -> None:
    await _ws.start()
    env.add_capability(_ws.capability("shell"))


@env.shutdown
async def _down() -> None:
    await _ws.stop()


@env.template(id="verilog_task")
async def verilog_task(task_id: str, validate_mode: str | None = None):
    """Reset the workspace to the task baseline, prompt the agent, then grade with the
    track's hidden grader (verilator/yosys/cocotb/SymbiYosys + mutant-kill + rubric)."""
    setup_meta = setup_task(task_id, validate_mode=validate_mode)
    answer = yield TASK_SPECS_BY_ID[task_id].prompt

    evaluation = evaluate_task(task_id)
    info = dict(evaluation.info or {})
    info["setup"] = setup_meta
    info["final_answer"] = None if answer is None else str(answer)
    evaluation.info = info
    yield evaluation
