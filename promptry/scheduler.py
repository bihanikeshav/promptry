"""Background scheduler for running eval suites on a loop.

Starts a subprocess that periodically imports a module, runs a suite,
and checks for drift. Manages state via a PID file.

Works on both Windows and Unix.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTRY_DIR = Path.home() / ".promptry"
_PID_FILE = _PROMPTRY_DIR / "monitor.pid"
_LOG_FILE = _PROMPTRY_DIR / "monitor.log"
_STATE_FILE = _PROMPTRY_DIR / "monitor.json"


def _ensure_dir():
    _PROMPTRY_DIR.mkdir(parents=True, exist_ok=True)


# ---- public API ----

def start(suite_name: str, module: str, interval: int = 1440):
    """Start the background monitor.

    interval is in minutes. Spawns a subprocess and writes
    the PID to ~/.promptry/monitor.pid.
    """
    if is_running():
        raise RuntimeError("Monitor is already running (PID file exists)")

    _ensure_dir()

    # build the command that the subprocess will run
    cmd = [
        sys.executable, "-m", "promptry.scheduler",
        "--suite", suite_name,
        "--module", module,
        "--interval", str(interval),
    ]

    kwargs = {}
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True

    log_fh = open(_LOG_FILE, "a")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    finally:
        log_fh.close()

    _PID_FILE.write_text(str(proc.pid))

    # save config so status can report what's running
    state = {
        "suite": suite_name,
        "module": module,
        "interval_minutes": interval,
        "started_at": datetime.now().isoformat(),
        "pid": proc.pid,
    }
    _STATE_FILE.write_text(json.dumps(state, indent=2))

    return proc.pid


def stop():
    """Stop the background monitor."""
    if not _PID_FILE.exists():
        raise RuntimeError("No monitor running (no PID file)")

    pid = int(_PID_FILE.read_text().strip())

    try:
        if sys.platform == "win32":
            # on Windows os.kill with SIGTERM calls TerminateProcess (hard kill).
            # there is no graceful signal on Windows for non-console processes.
            os.kill(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass  # already dead

    _PID_FILE.unlink(missing_ok=True)
    return pid


def is_running() -> bool:
    """Check if the monitor process is alive."""
    if not _PID_FILE.exists():
        return False

    pid = int(_PID_FILE.read_text().strip())
    return _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    if sys.platform == "win32":
        # os.kill(pid, 0) doesn't work reliably on Windows.
        # Use ctypes to call OpenProcess and check the result.
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # stale PID
        _PID_FILE.unlink(missing_ok=True)
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            _PID_FILE.unlink(missing_ok=True)
            return False


def status() -> dict | None:
    """Get monitor status. Returns None if not running."""
    if not is_running():
        return None

    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text())

    return {"running": True}


# ---- the actual loop (runs inside the subprocess) ----

def _run_loop(suite_name: str, module: str, interval_minutes: int):
    """Main loop for the background monitor process.

    Imports the module, runs the suite, checks drift, sleeps, repeat.
    """
    import importlib
    from promptry.runner import run_suite
    from promptry.drift import DriftMonitor

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    log.info("monitor started: suite=%s module=%s interval=%dm",
             suite_name, module, interval_minutes)

    interval_seconds = interval_minutes * 60
    monitor = DriftMonitor()

    while True:
        try:
            # re-import each cycle in case the module changed
            mod = importlib.import_module(module)
            importlib.reload(mod)

            result = run_suite(suite_name)
            drift = monitor.check(suite_name)

            log.info(
                "run complete: pass=%s score=%.3f drift=%s",
                result.overall_pass, result.overall_score, drift.is_drifting,
            )

            # notify on regression or drift
            if not result.overall_pass or drift.is_drifting:
                from promptry.notifications import notify_regression
                details = f"Drift: {drift.message}" if drift.is_drifting else ""
                notify_regression(result, details=details)

            # update state file with last run info
            _ensure_dir()
            state = {}
            if _STATE_FILE.exists():
                state = json.loads(_STATE_FILE.read_text())
            state["last_run"] = datetime.now().isoformat()
            state["last_score"] = result.overall_score
            state["last_pass"] = result.overall_pass
            state["drifting"] = drift.is_drifting
            _STATE_FILE.write_text(json.dumps(state, indent=2))

        except Exception:
            log.exception("monitor run failed")

        time.sleep(interval_seconds)


# ---- entry point for subprocess ----

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--interval", type=int, default=1440)
    args = parser.parse_args()

    _run_loop(args.suite, args.module, args.interval)
