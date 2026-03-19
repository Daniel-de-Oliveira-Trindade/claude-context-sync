"""
watcher.py — File watcher daemon for automatic session sync.

Monitors ~/.claude/projects/**/*.jsonl for modifications.
After a debounce period (default 30s) of inactivity, triggers sync-push --auto
for each modified session.

Usage:
    from .watcher import SessionWatcher
    watcher = SessionWatcher(repo_url, debounce_seconds=30)
    watcher.start()   # blocks
"""

import os
import sys
import json
import time
import signal
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
PID_FILE = Path.home() / ".claude-context-sync" / "watch.pid"
LOG_FILE = Path.home() / ".claude-context-sync" / "logs" / "watch.log"
LAST_SYNC_FILE = Path.home() / ".claude-context-sync" / "watch-last-sync.json"


def _log(message: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {message}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def _get_session_id_from_path(path: str) -> Optional[str]:
    """Extract session UUID from .jsonl file path."""
    p = Path(path)
    if p.suffix == ".jsonl":
        name = p.stem
        # basic UUID format check
        if len(name) == 36 and name.count("-") == 4:
            return name
    return None


def _resolve_executable() -> str:
    """Find the claude-sync executable (same logic as hooks.py)."""
    # 1. Same directory as this script (bundled binary)
    candidate = Path(sys.executable).parent / "claude-sync"
    if candidate.exists():
        return str(candidate)
    candidate_exe = Path(sys.executable).parent / "claude-sync.exe"
    if candidate_exe.exists():
        return str(candidate_exe)

    # 2. Scripts directory (pip install)
    scripts = Path(sys.executable).parent / "Scripts"
    for name in ("claude-sync.exe", "claude-sync"):
        c = scripts / name
        if c.exists():
            return str(c)

    # 3. Fall back to PATH
    return "claude-sync"


def _record_last_sync(session_id: str, status: str):
    LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if LAST_SYNC_FILE.exists():
        try:
            data = json.loads(LAST_SYNC_FILE.read_text())
        except Exception:
            pass
    data["last_session"] = session_id
    data["last_status"] = status
    data["last_time"] = datetime.now().isoformat()
    LAST_SYNC_FILE.write_text(json.dumps(data, indent=2))


def _push_session(session_id: str, repo_url: Optional[str]):
    exe = _resolve_executable()
    args = [exe, "sync-push", "--session", session_id, "--auto", "--compress"]
    if repo_url:
        args += ["--repo", repo_url]
    _log(f"Pushing session {session_id[:8]}...")
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            _log(f"  OK — {session_id[:8]}")
            _record_last_sync(session_id, "ok")
        else:
            err = (result.stderr or result.stdout or "").strip()
            _log(f"  FAIL — {session_id[:8]}: {err[:200]}")
            _record_last_sync(session_id, f"error: {err[:100]}")
    except subprocess.TimeoutExpired:
        _log(f"  TIMEOUT — {session_id[:8]}")
        _record_last_sync(session_id, "timeout")
    except Exception as e:
        _log(f"  ERROR — {session_id[:8]}: {e}")
        _record_last_sync(session_id, f"error: {e}")


_BaseHandler = FileSystemEventHandler if WATCHDOG_AVAILABLE else object


class _DebounceHandler(_BaseHandler):
    """Debounces .jsonl file change events and triggers sync-push."""

    def __init__(self, repo_url: Optional[str], debounce_seconds: float):
        super().__init__()
        self.repo_url = repo_url
        self.debounce_seconds = debounce_seconds
        self._pending: Dict[str, float] = {}  # session_id → last event time
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def on_modified(self, event):
        self._handle(event)

    def on_created(self, event):
        self._handle(event)

    def _handle(self, event):
        if event.is_directory:
            return
        session_id = _get_session_id_from_path(event.src_path)
        if session_id:
            with self._lock:
                self._pending[session_id] = time.monotonic()

    def _flush_loop(self):
        while True:
            time.sleep(5)
            now = time.monotonic()
            to_push = []
            with self._lock:
                for sid, last_t in list(self._pending.items()):
                    if now - last_t >= self.debounce_seconds:
                        to_push.append(sid)
                        del self._pending[sid]
            for sid in to_push:
                _push_session(sid, self.repo_url)


class SessionWatcher:
    """
    Watches ~/.claude/projects/ for .jsonl changes and auto-pushes modified sessions.

    Args:
        repo_url: Git repo URL (None = use configured default)
        debounce_seconds: Wait this long after last change before pushing (default 30s)
    """

    def __init__(self, repo_url: Optional[str] = None, debounce_seconds: float = 30.0):
        if not WATCHDOG_AVAILABLE:
            raise RuntimeError(
                "watchdog is not installed. Run: pip install watchdog"
            )
        self.repo_url = repo_url
        self.debounce_seconds = debounce_seconds
        self._observer: Optional[Observer] = None

    def start(self, blocking: bool = True):
        """Start watching. If blocking=True, runs until Ctrl-C or stop()."""
        if not CLAUDE_PROJECTS_DIR.exists():
            CLAUDE_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

        handler = _DebounceHandler(self.repo_url, self.debounce_seconds)
        self._observer = Observer()
        self._observer.schedule(handler, str(CLAUDE_PROJECTS_DIR), recursive=True)
        self._observer.start()
        _log(f"Watch started — monitoring {CLAUDE_PROJECTS_DIR} (debounce {self.debounce_seconds}s)")

        if blocking:
            try:
                while self._observer.is_alive():
                    time.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                self.stop()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
            _log("Watch stopped.")


# ---------------------------------------------------------------------------
# Daemon helpers (PID file management)
# ---------------------------------------------------------------------------

def write_pid():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def read_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def clear_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


def is_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_status() -> dict:
    """Return current watcher status dict."""
    pid = read_pid()
    running = pid is not None and is_running(pid)
    last_sync = {}
    if LAST_SYNC_FILE.exists():
        try:
            last_sync = json.loads(LAST_SYNC_FILE.read_text())
        except Exception:
            pass
    return {
        "running": running,
        "pid": pid if running else None,
        "last_session": last_sync.get("last_session"),
        "last_status": last_sync.get("last_status"),
        "last_time": last_sync.get("last_time"),
        "log_file": str(LOG_FILE),
    }
