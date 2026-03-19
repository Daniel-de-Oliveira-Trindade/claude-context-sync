"""
storage.py — Bundle storage on disk.

Layout:
  {DATA_DIR}/sessions/{username}/{project}/{bundle_file}

bundle_file format: {session_id}_{YYYYMMDD-HHMMSS}.bundle.gz[.enc]
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

DATA_DIR = Path(os.environ.get("SYNC_DATA_DIR", "/data"))
SESSIONS_DIR = DATA_DIR / "sessions"


def _user_dir(username: str) -> Path:
    return SESSIONS_DIR / username


def save_bundle(username: str, project: str, filename: str, data: bytes) -> Path:
    dest_dir = _user_dir(username) / project
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(data)
    return dest


def list_bundles(username: str, project: Optional[str] = None) -> list[dict]:
    """List all bundles for a user, optionally filtered by project."""
    base = _user_dir(username)
    if not base.exists():
        return []
    results = []
    projects = [base / project] if project else list(base.iterdir())
    for proj_dir in projects:
        if not proj_dir.is_dir():
            continue
        for f in sorted(proj_dir.iterdir()):
            if not f.is_file():
                continue
            results.append({
                "project": proj_dir.name,
                "filename": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "session_prefix": f.name[:8],
            })
    return results


def list_all_bundles() -> list[dict]:
    """List all bundles for all users (admin only)."""
    if not SESSIONS_DIR.exists():
        return []
    results = []
    for user_dir in SESSIONS_DIR.iterdir():
        if not user_dir.is_dir():
            continue
        for entry in list_bundles(user_dir.name):
            entry["username"] = user_dir.name
            results.append(entry)
    return results


def get_latest_bundle(username: str, session_prefix: str) -> Optional[Path]:
    """Return the most recent bundle matching the session prefix."""
    base = _user_dir(username)
    if not base.exists():
        return None
    candidates = []
    for proj_dir in base.iterdir():
        if not proj_dir.is_dir():
            continue
        for f in proj_dir.iterdir():
            if f.is_file() and f.name.startswith(session_prefix):
                candidates.append(f)
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def get_bundle_by_name(username: str, filename: str) -> Optional[Path]:
    """Return a specific bundle by exact filename."""
    base = _user_dir(username)
    if not base.exists():
        return None
    for proj_dir in base.iterdir():
        candidate = proj_dir / filename
        if candidate.exists():
            return candidate
    return None


def delete_bundle(username: str, session_prefix: str) -> int:
    """Delete all bundles matching the session prefix. Returns count deleted."""
    base = _user_dir(username)
    if not base.exists():
        return 0
    count = 0
    for proj_dir in base.iterdir():
        if not proj_dir.is_dir():
            continue
        for f in list(proj_dir.iterdir()):
            if f.is_file() and f.name.startswith(session_prefix):
                f.unlink()
                count += 1
    return count


def get_storage_stats() -> dict:
    """Return total storage usage stats."""
    if not SESSIONS_DIR.exists():
        return {"total_bytes": 0, "total_bundles": 0, "users": 0}
    total_bytes = 0
    total_bundles = 0
    users = 0
    for user_dir in SESSIONS_DIR.iterdir():
        if not user_dir.is_dir():
            continue
        users += 1
        for proj_dir in user_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            for f in proj_dir.iterdir():
                if f.is_file():
                    total_bytes += f.stat().st_size
                    total_bundles += 1
    return {"total_bytes": total_bytes, "total_bundles": total_bundles, "users": users}
