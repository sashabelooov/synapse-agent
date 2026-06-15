"""Cron scheduler — background thread that runs agent jobs on a schedule.

Jobs are defined in ~/.synapse/cron_jobs.json (or $CRON_JOBS_PATH).
Tick interval: 60 seconds. Jobs that fired in the last tick window and
haven't been run yet are dispatched to a thread pool.

Two pools:
  - parallel  — independent jobs run concurrently (default)
  - sequential — state-mutating jobs ("sequential": true) run one at a time

File-based lock prevents overlapping ticks across processes.
Jobs that exceed their timeout_s are hard-stopped via Future.cancel().

Delivery targets:
  - "telegram" — sends the reply as a Telegram message
  - "log"      — writes to the Python logger only
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path
from typing import Any

from croniter import croniter

from agent.runner import AgentState, run_agent_turn

log = logging.getLogger(__name__)

TICK_INTERVAL = 60       # seconds between ticks
DEFAULT_TIMEOUT = 120    # seconds per job
JOBS_FILENAME = "cron_jobs.json"

# Module-level singleton — set by start_scheduler(), read by the tool.
_scheduler: CronScheduler | None = None


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _synapse_home() -> Path:
    return Path(os.environ.get("SYNAPSE_HOME", Path.home() / ".synapse"))


def jobs_path() -> Path:
    custom = os.environ.get("CRON_JOBS_PATH", "").strip()
    if custom:
        return Path(custom)
    return _synapse_home() / JOBS_FILENAME


def _lock_path() -> Path:
    return _synapse_home() / "cron.lock"


# ---------------------------------------------------------------------------
# Job file I/O
# ---------------------------------------------------------------------------

def load_jobs(path: Path | None = None) -> dict[str, Any]:
    """Load job definitions from JSON. Returns {} if the file doesn't exist."""
    p = path or jobs_path()
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_jobs(jobs: dict[str, Any], path: Path | None = None) -> None:
    """Atomically write job definitions (temp → rename)."""
    p = path or jobs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(p)


# ---------------------------------------------------------------------------
# Schedule evaluation
# ---------------------------------------------------------------------------

def is_due(schedule: str, last_run_ts: float | None = None) -> bool:
    """Return True if the cron expression fired within the last TICK_INTERVAL seconds
    and the job hasn't already been run in that same window."""
    now = datetime.now()
    cron = croniter(schedule, now)
    prev: datetime = cron.get_prev(datetime)

    elapsed = (now - prev).total_seconds()
    if elapsed > TICK_INTERVAL:
        return False

    # Already ran after this scheduled time → skip
    if last_run_ts is not None and last_run_ts >= prev.timestamp():
        return False

    return True


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _deliver_telegram(text: str, job_name: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not token or not chat_id:
        log.warning(
            "Cron delivery=telegram but TELEGRAM_BOT_TOKEN or "
            "TELEGRAM_ALLOWED_USER_ID is not set."
        )
        return

    import requests

    header = f"\U0001f550 *Cron: {job_name}*\n\n"
    full = header + text
    for i in range(0, len(full), 4096):
        chunk = full[i : i + 4096]
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as exc:
            log.error("Telegram delivery failed for job '%s': %s", job_name, exc)


def deliver(delivery: str, job_name: str, text: str) -> None:
    """Route result to the configured delivery target."""
    if delivery == "telegram":
        _deliver_telegram(text, job_name)
    else:
        log.info("Cron job '%s' result:\n%s", job_name, text)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class CronScheduler:
    """Background thread that checks and runs scheduled jobs every 60 seconds."""

    def __init__(self, state: AgentState, path: Path | None = None) -> None:
        self._state = state
        self._path = path or jobs_path()
        self._stop = threading.Event()
        self._run_times: dict[str, float] = {}  # job name → last-run epoch

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._loop, daemon=True, name="cron-scheduler")
        t.start()
        log.info("Cron scheduler started (tick every %ds, jobs: %s).", TICK_INTERVAL, self._path)
        return t

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                log.error("Cron tick error: %s", exc)
            self._stop.wait(timeout=TICK_INTERVAL)

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self) -> list[str]:
        """Check all jobs; run those that are due. Returns list of fired job names."""
        lock_p = _lock_path()

        # File-based lock: skip tick if another process/thread is active.
        if lock_p.exists():
            age = time.time() - lock_p.stat().st_mtime
            if age < TICK_INTERVAL * 2:
                log.debug("Cron: lock file active (age %.0fs), skipping tick.", age)
                return []

        lock_p.parent.mkdir(parents=True, exist_ok=True)
        lock_p.touch()

        try:
            jobs = load_jobs(self._path)
            parallel: list[tuple[str, dict]] = []
            sequential: list[tuple[str, dict]] = []

            for name, cfg in jobs.items():
                if not cfg.get("enabled", True):
                    continue
                schedule = cfg.get("schedule", "")
                if not schedule:
                    continue
                try:
                    if not is_due(schedule, self._run_times.get(name)):
                        continue
                except Exception as exc:
                    log.error(
                        "Invalid cron expression '%s' for job '%s': %s",
                        schedule, name, exc,
                    )
                    continue

                (sequential if cfg.get("sequential", False) else parallel).append((name, cfg))

            fired: list[str] = []

            # Parallel pool
            if parallel:
                with ThreadPoolExecutor(max_workers=len(parallel)) as pool:
                    futures: dict[Future, tuple[str, dict]] = {
                        pool.submit(self._run_job, n, c): (n, c)
                        for n, c in parallel
                    }
                    for fut, (name, cfg) in futures.items():
                        timeout = cfg.get("timeout_s", DEFAULT_TIMEOUT)
                        try:
                            fut.result(timeout=timeout)
                            self._run_times[name] = time.time()
                            fired.append(name)
                        except FutureTimeout:
                            fut.cancel()
                            log.error(
                                "Cron job '%s' timed out after %ds.", name, timeout
                            )
                        except Exception as exc:
                            log.error("Cron job '%s' failed: %s", name, exc)

            # Sequential pool (one at a time)
            for name, cfg in sequential:
                timeout = cfg.get("timeout_s", DEFAULT_TIMEOUT)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(self._run_job, name, cfg)
                    try:
                        fut.result(timeout=timeout)
                        self._run_times[name] = time.time()
                        fired.append(name)
                    except FutureTimeout:
                        fut.cancel()
                        log.error(
                            "Cron job '%s' timed out after %ds.", name, timeout
                        )
                    except Exception as exc:
                        log.error("Cron job '%s' failed: %s", name, exc)

            return fired

        finally:
            try:
                lock_p.unlink()
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    def _run_job(self, name: str, cfg: dict) -> None:
        """Execute one job: agent turn → deliver result."""
        prompt = cfg.get("prompt", "").strip()
        delivery = cfg.get("delivery", "log")

        if not prompt:
            log.warning("Cron job '%s' has no prompt; skipping.", name)
            return

        log.info("Cron job '%s' starting …", name)

        # Isolated session per job — no shared message history.
        messages: list[dict] = [{"role": "system", "content": self._state.system_prompt}]

        # Set cron context flag so the cronjob tool can block dangerous actions.
        old = os.environ.get("SYNAPSE_CRON_CONTEXT")
        os.environ["SYNAPSE_CRON_CONTEXT"] = "1"
        try:
            reply, _ = run_agent_turn(prompt, messages, self._state)
        finally:
            if old is None:
                os.environ.pop("SYNAPSE_CRON_CONTEXT", None)
            else:
                os.environ["SYNAPSE_CRON_CONTEXT"] = old

        log.info("Cron job '%s' complete (%d chars).", name, len(reply))
        deliver(delivery, name, reply)

    def run_now(self, name: str) -> str:
        """Immediately run a named job outside the tick cycle. Returns result text."""
        jobs = load_jobs(self._path)
        if name not in jobs:
            return f"Error: job '{name}' not found."
        cfg = jobs[name]
        try:
            self._run_job(name, cfg)
            return f"Job '{name}' executed."
        except Exception as exc:
            return f"Error running job '{name}': {exc}"


# ---------------------------------------------------------------------------
# Singleton API used by the cronjob tool
# ---------------------------------------------------------------------------

def start_scheduler(state: AgentState, path: Path | None = None) -> CronScheduler:
    """Create, start, and register the global scheduler. Call once at startup."""
    global _scheduler
    _scheduler = CronScheduler(state, path)
    _scheduler.start()
    return _scheduler


def get_scheduler() -> CronScheduler | None:
    return _scheduler
