"""cronjob tool — manage scheduled agent jobs.

Actions:
  list      — show all jobs with status and next run time
  add       — create a new job
  enable    — enable a disabled job
  disable   — disable a job without deleting it
  delete    — permanently remove a job
  run_now   — execute a job immediately, outside the schedule

Security: when SYNAPSE_CRON_CONTEXT=1 (i.e. we're already inside a cron job),
add and delete are blocked to prevent runaway scheduling loops.
"""

from __future__ import annotations

import os
from datetime import datetime

from croniter import croniter

from cron.scheduler import get_scheduler, load_jobs, save_jobs
from tools.base.tool import ToolDefinition

_BLOCKED_IN_CRON = {"add", "delete"}


def _in_cron_context() -> bool:
    return os.environ.get("SYNAPSE_CRON_CONTEXT", "") == "1"


def _next_run(schedule: str) -> str:
    try:
        cron = croniter(schedule, datetime.now())
        nxt: datetime = cron.get_next(datetime)
        return nxt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "invalid schedule"


def _cronjob(action: str, name: str = "", schedule: str = "", prompt: str = "",
             delivery: str = "telegram", sequential: bool = False,
             timeout_s: int = 120) -> str:
    action = action.strip().lower()

    if _in_cron_context() and action in _BLOCKED_IN_CRON:
        return (
            f"Error: '{action}' is not allowed inside a running cron job "
            "(prevents runaway scheduling loops)."
        )

    jobs = load_jobs()

    # --- list ---
    if action == "list":
        if not jobs:
            return "No cron jobs configured. Use action='add' to create one."
        lines = []
        for jname, cfg in jobs.items():
            status = "✅ enabled" if cfg.get("enabled", True) else "⏸ disabled"
            sched = cfg.get("schedule", "?")
            nxt = _next_run(sched) if cfg.get("enabled", True) else "-"
            lines.append(
                f"• **{jname}** [{status}]\n"
                f"  schedule: {sched}  next: {nxt}\n"
                f"  delivery: {cfg.get('delivery', 'log')}  "
                f"timeout: {cfg.get('timeout_s', 120)}s  "
                f"sequential: {cfg.get('sequential', False)}\n"
                f"  prompt: {cfg.get('prompt', '')[:80]}…"
            )
        return "\n\n".join(lines)

    # --- add ---
    if action == "add":
        if not name:
            return "Error: 'name' is required for action='add'."
        if not schedule:
            return "Error: 'schedule' (cron expression) is required for action='add'."
        if not prompt:
            return "Error: 'prompt' is required for action='add'."
        try:
            croniter(schedule)
        except Exception as exc:
            return f"Error: invalid cron expression '{schedule}': {exc}"
        if name in jobs:
            return f"Error: job '{name}' already exists. Use action='delete' first."

        jobs[name] = {
            "schedule": schedule,
            "prompt": prompt,
            "delivery": delivery,
            "enabled": True,
            "sequential": sequential,
            "timeout_s": timeout_s,
        }
        save_jobs(jobs)
        nxt = _next_run(schedule)
        return f"Job '{name}' created. Next run: {nxt}."

    # --- enable ---
    if action == "enable":
        if name not in jobs:
            return f"Error: job '{name}' not found."
        jobs[name]["enabled"] = True
        save_jobs(jobs)
        return f"Job '{name}' enabled. Next run: {_next_run(jobs[name]['schedule'])}."

    # --- disable ---
    if action == "disable":
        if name not in jobs:
            return f"Error: job '{name}' not found."
        jobs[name]["enabled"] = False
        save_jobs(jobs)
        return f"Job '{name}' disabled."

    # --- delete ---
    if action == "delete":
        if name not in jobs:
            return f"Error: job '{name}' not found."
        del jobs[name]
        save_jobs(jobs)
        return f"Job '{name}' deleted."

    # --- run_now ---
    if action == "run_now":
        if name not in jobs:
            return f"Error: job '{name}' not found."
        scheduler = get_scheduler()
        if scheduler is None:
            return "Error: scheduler is not running (start the agent first)."
        return scheduler.run_now(name)

    return (
        f"Error: unknown action '{action}'. "
        "Valid actions: list, add, enable, disable, delete, run_now."
    )


tool = ToolDefinition(
    name="cronjob",
    description=(
        "Manage scheduled agent jobs (cron). "
        "Actions: list (show all jobs), add (create a new job with a cron schedule "
        "and a prompt the agent will run automatically), enable/disable (toggle a job), "
        "delete (remove a job), run_now (execute immediately outside the schedule). "
        "Example schedule: '0 9 * * *' = daily at 09:00, '*/30 * * * *' = every 30 min."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "list | add | enable | disable | delete | run_now",
            },
            "name": {
                "type": "string",
                "description": "Job name (required for all actions except list).",
            },
            "schedule": {
                "type": "string",
                "description": "Standard 5-field cron expression (required for add).",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt the agent will run on schedule (required for add).",
            },
            "delivery": {
                "type": "string",
                "description": "Result delivery target: 'telegram' (default) or 'log'.",
            },
            "sequential": {
                "type": "boolean",
                "description": (
                    "If true, this job runs in the sequential pool — safe for state-mutating "
                    "operations. Default false (parallel pool)."
                ),
            },
            "timeout_s": {
                "type": "integer",
                "description": "Hard timeout in seconds. Job is killed if exceeded. Default 120.",
            },
        },
        "required": ["action"],
    },
    function=_cronjob,
)
