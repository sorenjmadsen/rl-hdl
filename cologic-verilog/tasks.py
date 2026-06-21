"""Tasks for the verilog-template chip-design environment.

Run locally:  hud eval tasks.py claude --task-ids stream-arb-fifo-repair --group 1 -y

One generic ``verilog_task`` template (in env.py) is bound once per spec in the catalog.
``env`` is re-exported because ``hud eval tasks.py`` serves THIS module as the env source.
"""


from env import env, verilog_task  # noqa: F401  (env re-exported for `hud eval tasks.py`)
from task_catalog import TASK_SPECS

# Public LIST the taskset scanner collects. Intermediates are underscore-prefixed so the
# scanner doesn't also collect them as standalone Tasks (-> "duplicate task slugs").
tasks = []

for _spec in TASK_SPECS:
    _task = verilog_task(task_id=_spec.task_id)  # calling the template mints a Task
    _task.slug = _spec.slug
    _task.columns = {  # v6 uses `columns` (filterable facets); v5 used `metadata`
        "task_id": _spec.task_id,
        "track": _spec.track,
        "variant": _spec.variant,
        "language": _spec.language,
        "toolchain": _spec.toolchain,
        "module": _spec.module,
    }
    tasks.append(_task)
