"""Tests for cron/scheduler.py and tools/cronjob/cronjob.py."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from croniter import croniter

from cron.scheduler import (
    CronScheduler,
    TICK_INTERVAL,
    deliver,
    is_due,
    load_jobs,
    save_jobs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state() -> MagicMock:
    state = MagicMock()
    state.system_prompt = "You are Synapse."
    return state


def _always_due_schedule() -> str:
    """Return a cron expression whose last fire time was just now."""
    now = datetime.now()
    return f"{now.minute} {now.hour} {now.day} {now.month} *"


# ---------------------------------------------------------------------------
# load_jobs / save_jobs
# ---------------------------------------------------------------------------

class TestJobsIO:
    def test_load_missing_returns_empty(self, tmp_path):
        result = load_jobs(tmp_path / "nonexistent.json")
        assert result == {}

    def test_roundtrip(self, tmp_path):
        jobs = {
            "test_job": {
                "schedule": "0 9 * * *",
                "prompt": "Hello",
                "delivery": "telegram",
                "enabled": True,
            }
        }
        p = tmp_path / "jobs.json"
        save_jobs(jobs, p)
        loaded = load_jobs(p)
        assert loaded == jobs

    def test_atomic_write_uses_tmp(self, tmp_path):
        p = tmp_path / "jobs.json"
        save_jobs({"a": {}}, p)
        assert p.exists()
        assert not (tmp_path / "jobs.tmp").exists()

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "jobs.json"
        save_jobs({}, p)
        assert p.exists()


# ---------------------------------------------------------------------------
# is_due
# ---------------------------------------------------------------------------

class TestIsDue:
    def test_due_when_fired_within_tick(self):
        # "every minute" always fires within the last 60 seconds
        assert is_due("* * * * *") is True

    def test_not_due_when_fired_more_than_tick_ago(self):
        # Daily at midnight — if it's not midnight right now, it won't be due
        now = datetime.now()
        if now.hour != 0 or now.minute != 0:
            assert is_due("0 0 * * *") is False

    def test_not_due_when_already_ran(self):
        # Mark last run as "just now" — should not re-fire
        assert is_due("* * * * *", last_run_ts=time.time()) is False

    def test_due_when_last_run_was_before_prev_fire(self):
        # last ran 2 minutes ago → the most recent scheduled time was ≤60s ago
        # and the last run predates it → should be due
        old_ts = time.time() - 120
        assert is_due("* * * * *", last_run_ts=old_ts) is True

    def test_not_due_when_last_run_after_prev_fire(self):
        # Compute the actual previous fire time and set last_run_ts to just after it.
        schedule = "* * * * *"
        cron = croniter(schedule, datetime.now())
        prev: datetime = cron.get_prev(datetime)
        last_run_ts = prev.timestamp() + 1  # ran 1 second after the scheduled fire
        assert is_due(schedule, last_run_ts=last_run_ts) is False


# ---------------------------------------------------------------------------
# CronScheduler — tick logic
# ---------------------------------------------------------------------------

class TestCronSchedulerTick:
    def _jobs_file(self, tmp_path: Path, jobs: dict) -> Path:
        p = tmp_path / "jobs.json"
        save_jobs(jobs, p)
        return p

    def test_due_job_is_fired(self, tmp_path):
        jobs = {
            "my_job": {
                "schedule": "* * * * *",  # every minute — always due
                "prompt": "Say hello",
                "delivery": "log",
                "enabled": True,
            }
        }
        p = self._jobs_file(tmp_path, jobs)
        state = _make_state()

        with patch("cron.scheduler.run_agent_turn", return_value=("Hello!", {})):
            scheduler = CronScheduler(state, p)
            fired = scheduler.tick()

        assert "my_job" in fired

    def test_disabled_job_skipped(self, tmp_path):
        jobs = {
            "disabled": {
                "schedule": "* * * * *",
                "prompt": "Say hello",
                "delivery": "log",
                "enabled": False,
            }
        }
        p = self._jobs_file(tmp_path, jobs)
        state = _make_state()

        with patch("cron.scheduler.run_agent_turn", return_value=("Hi", {})):
            scheduler = CronScheduler(state, p)
            fired = scheduler.tick()

        assert "disabled" not in fired

    def test_already_run_job_skipped(self, tmp_path):
        jobs = {
            "recent": {
                "schedule": "* * * * *",
                "prompt": "Check stuff",
                "delivery": "log",
                "enabled": True,
            }
        }
        p = self._jobs_file(tmp_path, jobs)
        state = _make_state()

        with patch("cron.scheduler.run_agent_turn", return_value=("Done", {})):
            scheduler = CronScheduler(state, p)
            scheduler._run_times["recent"] = time.time()  # just ran
            fired = scheduler.tick()

        assert "recent" not in fired

    def test_lock_file_prevents_tick(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SYNAPSE_HOME", str(tmp_path))
        lock = tmp_path / "cron.lock"
        lock.touch()

        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "jobs.json")
        fired = scheduler.tick()

        assert fired == []
        lock.unlink()  # cleanup

    def test_lock_file_stale_allows_tick(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SYNAPSE_HOME", str(tmp_path))
        jobs = {
            "job": {
                "schedule": "* * * * *",
                "prompt": "Go",
                "delivery": "log",
                "enabled": True,
            }
        }
        p = self._jobs_file(tmp_path, jobs)

        # Create a stale lock (older than 2 × TICK_INTERVAL)
        lock = tmp_path / "cron.lock"
        lock.touch()
        stale_mtime = time.time() - (TICK_INTERVAL * 3)
        os.utime(lock, (stale_mtime, stale_mtime))

        state = _make_state()
        with patch("cron.scheduler.run_agent_turn", return_value=("OK", {})):
            scheduler = CronScheduler(state, p)
            fired = scheduler.tick()

        assert "job" in fired

    def test_run_times_updated_after_success(self, tmp_path):
        jobs = {
            "track_me": {
                "schedule": "* * * * *",
                "prompt": "Do it",
                "delivery": "log",
                "enabled": True,
            }
        }
        p = self._jobs_file(tmp_path, jobs)
        state = _make_state()

        before = time.time()
        with patch("cron.scheduler.run_agent_turn", return_value=("OK", {})):
            scheduler = CronScheduler(state, p)
            scheduler.tick()
        after = time.time()

        assert "track_me" in scheduler._run_times
        assert before <= scheduler._run_times["track_me"] <= after

    def test_timeout_kills_slow_job(self, tmp_path):
        jobs = {
            "slow": {
                "schedule": "* * * * *",
                "prompt": "Sleep forever",
                "delivery": "log",
                "enabled": True,
                "timeout_s": 1,
            }
        }
        p = self._jobs_file(tmp_path, jobs)
        state = _make_state()

        def _slow(*a, **kw):
            time.sleep(10)
            return ("done", {})

        with patch("cron.scheduler.run_agent_turn", side_effect=_slow):
            scheduler = CronScheduler(state, p)
            fired = scheduler.tick()

        assert "slow" not in fired  # timed out → not in fired list

    def test_sequential_job_runs_after_parallel(self, tmp_path):
        jobs = {
            "par": {
                "schedule": "* * * * *",
                "prompt": "Parallel",
                "delivery": "log",
                "enabled": True,
                "sequential": False,
            },
            "seq": {
                "schedule": "* * * * *",
                "prompt": "Sequential",
                "delivery": "log",
                "enabled": True,
                "sequential": True,
            },
        }
        p = self._jobs_file(tmp_path, jobs)
        state = _make_state()

        with patch("cron.scheduler.run_agent_turn", return_value=("OK", {})):
            scheduler = CronScheduler(state, p)
            fired = scheduler.tick()

        assert "par" in fired
        assert "seq" in fired

    def test_empty_jobs_fires_nothing(self, tmp_path):
        p = tmp_path / "jobs.json"
        save_jobs({}, p)
        state = _make_state()
        scheduler = CronScheduler(state, p)
        fired = scheduler.tick()
        assert fired == []

    def test_missing_jobs_file_fires_nothing(self, tmp_path):
        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "absent.json")
        fired = scheduler.tick()
        assert fired == []


# ---------------------------------------------------------------------------
# CronScheduler — _run_job
# ---------------------------------------------------------------------------

class TestRunJob:
    def test_prompt_sent_to_agent(self, tmp_path):
        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "jobs.json")
        received: list[str] = []

        def fake_turn(prompt, messages, st, **kw):
            received.append(prompt)
            return ("Reply", {})

        with patch("cron.scheduler.run_agent_turn", side_effect=fake_turn):
            scheduler._run_job("j", {"prompt": "What time is it?", "delivery": "log"})

        assert received[0] == "What time is it?"

    def test_cron_context_flag_set_during_run(self, tmp_path):
        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "jobs.json")
        observed: list[str] = []

        def fake_turn(prompt, messages, st, **kw):
            observed.append(os.environ.get("SYNAPSE_CRON_CONTEXT", ""))
            return ("Reply", {})

        with patch("cron.scheduler.run_agent_turn", side_effect=fake_turn):
            scheduler._run_job("j", {"prompt": "Hi", "delivery": "log"})

        assert observed == ["1"]

    def test_cron_context_flag_cleared_after_run(self, tmp_path):
        os.environ.pop("SYNAPSE_CRON_CONTEXT", None)
        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "jobs.json")

        with patch("cron.scheduler.run_agent_turn", return_value=("OK", {})):
            scheduler._run_job("j", {"prompt": "Hi", "delivery": "log"})

        assert "SYNAPSE_CRON_CONTEXT" not in os.environ

    def test_empty_prompt_skips_run(self, tmp_path):
        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "jobs.json")

        with patch("cron.scheduler.run_agent_turn") as mock_turn:
            scheduler._run_job("j", {"prompt": "", "delivery": "log"})
            mock_turn.assert_not_called()

    def test_deliver_called_with_reply(self, tmp_path):
        state = _make_state()
        scheduler = CronScheduler(state, tmp_path / "jobs.json")
        delivered: list = []

        with patch("cron.scheduler.run_agent_turn", return_value=("My result", {})):
            with patch("cron.scheduler.deliver", side_effect=lambda d, n, t: delivered.append(t)):
                scheduler._run_job("j", {"prompt": "Do it", "delivery": "telegram"})

        assert delivered == ["My result"]


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

class TestDeliver:
    def test_log_delivery_does_not_call_requests(self):
        with patch("requests.post") as mock_post:
            deliver("log", "my_job", "some text")
            mock_post.assert_not_called()

    def test_telegram_delivery_missing_token_skips(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)
        with patch("requests.post") as mock_post:
            deliver("telegram", "my_job", "hello")
            mock_post.assert_not_called()

    def test_telegram_delivery_calls_api(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "12345")
        with patch("requests.post") as mock_post:
            deliver("telegram", "my_job", "hello")
            mock_post.assert_called_once()
            url = mock_post.call_args[0][0]
            assert "test-token" in url


# ---------------------------------------------------------------------------
# cronjob tool
# ---------------------------------------------------------------------------

class TestCronjobTool:
    def _patch_jobs(self, tmp_path: Path, jobs: dict):
        p = tmp_path / "jobs.json"
        save_jobs(jobs, p)
        return p

    def _call(self, tmp_path, action, **kwargs):
        p = tmp_path / "jobs.json"
        if not p.exists():
            save_jobs({}, p)
        # load_jobs/save_jobs inside the tool call cron.scheduler.jobs_path()
        with patch("cron.scheduler.jobs_path", return_value=p):
            from tools.cronjob.cronjob import _cronjob
            return _cronjob(action, **kwargs)

    def test_list_empty(self, tmp_path):
        result = self._call(tmp_path, "list")
        assert "No cron jobs" in result

    def test_add_creates_job(self, tmp_path):
        result = self._call(
            tmp_path, "add",
            name="test",
            schedule="0 9 * * *",
            prompt="Morning check",
        )
        assert "created" in result
        p = tmp_path / "jobs.json"
        jobs = load_jobs(p)
        assert "test" in jobs

    def test_add_invalid_schedule_returns_error(self, tmp_path):
        result = self._call(
            tmp_path, "add",
            name="bad",
            schedule="not-a-cron",
            prompt="Run me",
        )
        assert result.startswith("Error:")

    def test_add_duplicate_returns_error(self, tmp_path):
        self._call(tmp_path, "add", name="dupe", schedule="* * * * *", prompt="A")
        result = self._call(tmp_path, "add", name="dupe", schedule="* * * * *", prompt="B")
        assert result.startswith("Error:") and "already exists" in result

    def test_add_missing_name_returns_error(self, tmp_path):
        result = self._call(tmp_path, "add", schedule="* * * * *", prompt="A")
        assert result.startswith("Error:") and "name" in result

    def test_add_missing_schedule_returns_error(self, tmp_path):
        result = self._call(tmp_path, "add", name="j", prompt="A")
        assert result.startswith("Error:") and "schedule" in result

    def test_add_missing_prompt_returns_error(self, tmp_path):
        result = self._call(tmp_path, "add", name="j", schedule="* * * * *")
        assert result.startswith("Error:") and "prompt" in result

    def test_enable_job(self, tmp_path):
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="Go")
        # Disable first
        self._call(tmp_path, "disable", name="j")
        result = self._call(tmp_path, "enable", name="j")
        assert "enabled" in result
        jobs = load_jobs(tmp_path / "jobs.json")
        assert jobs["j"]["enabled"] is True

    def test_disable_job(self, tmp_path):
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="Go")
        result = self._call(tmp_path, "disable", name="j")
        assert "disabled" in result
        jobs = load_jobs(tmp_path / "jobs.json")
        assert jobs["j"]["enabled"] is False

    def test_delete_job(self, tmp_path):
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="Go")
        result = self._call(tmp_path, "delete", name="j")
        assert "deleted" in result
        jobs = load_jobs(tmp_path / "jobs.json")
        assert "j" not in jobs

    def test_list_shows_jobs(self, tmp_path):
        self._call(tmp_path, "add", name="morning", schedule="0 9 * * *", prompt="Good morning")
        result = self._call(tmp_path, "list")
        assert "morning" in result
        assert "0 9 * * *" in result

    def test_enable_nonexistent_returns_error(self, tmp_path):
        result = self._call(tmp_path, "enable", name="ghost")
        assert result.startswith("Error:") and "not found" in result

    def test_delete_nonexistent_returns_error(self, tmp_path):
        result = self._call(tmp_path, "delete", name="ghost")
        assert result.startswith("Error:") and "not found" in result

    def test_unknown_action_returns_error(self, tmp_path):
        result = self._call(tmp_path, "fly")
        assert result.startswith("Error:") and "unknown action" in result

    def test_add_blocked_in_cron_context(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CRON_CONTEXT", "1")
        result = self._call(
            tmp_path, "add", name="j", schedule="* * * * *", prompt="A"
        )
        assert result.startswith("Error:") and "not allowed" in result

    def test_delete_blocked_in_cron_context(self, tmp_path, monkeypatch):
        # First add a job without cron context
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="A")
        # Now try delete in cron context
        monkeypatch.setenv("SYNAPSE_CRON_CONTEXT", "1")
        result = self._call(tmp_path, "delete", name="j")
        assert result.startswith("Error:") and "not allowed" in result

    def test_enable_allowed_in_cron_context(self, tmp_path, monkeypatch):
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="A")
        monkeypatch.setenv("SYNAPSE_CRON_CONTEXT", "1")
        result = self._call(tmp_path, "enable", name="j")
        assert "Error" not in result or "not allowed" not in result

    def test_run_now_no_scheduler_returns_error(self, tmp_path):
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="A")
        with patch("tools.cronjob.cronjob.get_scheduler", return_value=None):
            result = self._call(tmp_path, "run_now", name="j")
        assert result.startswith("Error:") and "not running" in result

    def test_run_now_invokes_scheduler(self, tmp_path):
        self._call(tmp_path, "add", name="j", schedule="* * * * *", prompt="A")
        mock_scheduler = MagicMock()
        mock_scheduler.run_now.return_value = "Job 'j' executed."
        with patch("tools.cronjob.cronjob.get_scheduler", return_value=mock_scheduler):
            result = self._call(tmp_path, "run_now", name="j")
        assert "executed" in result
        mock_scheduler.run_now.assert_called_once_with("j")
