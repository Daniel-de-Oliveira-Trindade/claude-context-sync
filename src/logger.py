"""
Logger - Centralized logging for Claude Context Sync

Two log files in ~/.claude-context-sync/logs/:
- hook.log: everything that runs via automatic hooks (always active)
- app.log: verbose output from manual commands (only when --verbose is passed)

Rotation: if a log file exceeds 1MB, it is renamed to *.log.1 and a new file is created.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

LOG_DIR = Path.home() / ".claude-context-sync" / "logs"
HOOK_LOG = LOG_DIR / "hook.log"
APP_LOG = LOG_DIR / "app.log"
MAX_LOG_SIZE = 1 * 1024 * 1024  # 1 MB

# Global flag — set to True when --verbose is passed
_verbose = False


def set_verbose(enabled: bool) -> None:
    """Enable or disable verbose (app) logging."""
    global _verbose
    _verbose = enabled


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _rotate_if_needed(log_path: Path) -> None:
    """Rename log to .1 if it exceeds MAX_LOG_SIZE."""
    if log_path.exists() and log_path.stat().st_size >= MAX_LOG_SIZE:
        rotated = log_path.with_suffix(log_path.suffix + ".1")
        log_path.rename(rotated)


def _write(log_path: Path, level: str, message: str) -> None:
    _ensure_log_dir()
    _rotate_if_needed(log_path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level:<5}] {message}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def log_hook(command: str, session_id: str, status: str, error: Optional[Exception] = None) -> None:
    """
    Log a hook execution result to hook.log.

    Args:
        command: The command that ran (e.g. "sync-push", "sync-pull")
        session_id: Session UUID or identifier (may be empty for sync-pull)
        status: "OK" or "ERROR"
        error: Exception instance if status is "ERROR"
    """
    session_part = f" session={session_id[:8]}" if session_id else ""
    if error:
        message = f"SessionHook: {command}{session_part} \u2192 {type(error).__name__}: {error}"
        _write(HOOK_LOG, "ERROR", message)
    else:
        message = f"SessionHook: {command}{session_part} \u2192 OK"
        _write(HOOK_LOG, "INFO", message)


def log_app(message: str, level: str = "INFO") -> None:
    """
    Log a message to app.log. Only writes if verbose mode is enabled.

    Args:
        message: Log message
        level: Log level string ("INFO", "ERROR", "WARN")
    """
    if not _verbose:
        return
    _write(APP_LOG, level, message)
