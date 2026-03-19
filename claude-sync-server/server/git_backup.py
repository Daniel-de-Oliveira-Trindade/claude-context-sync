"""
git_backup.py — Auto-commit bundles to a backup git repo.

When SYNC_GIT_BACKUP_REPO is set in environment, every new bundle upload
is committed and pushed to that repo automatically.
"""

import os
import threading
from pathlib import Path
from typing import Optional

BACKUP_REPO_URL = os.environ.get("SYNC_GIT_BACKUP_REPO", "")
BACKUP_REPO_DIR = Path(os.environ.get("SYNC_DATA_DIR", "/data")) / "git-backup"

_lock = threading.Lock()


def _get_repo():
    try:
        import git
    except ImportError:
        return None

    if not BACKUP_REPO_URL:
        return None

    if not (BACKUP_REPO_DIR / ".git").exists():
        BACKUP_REPO_DIR.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(BACKUP_REPO_DIR)
        repo.create_remote("origin", BACKUP_REPO_URL)
        try:
            repo.remotes.origin.pull("main")
        except Exception:
            pass
        return repo

    return git.Repo(BACKUP_REPO_DIR)


def backup_bundle(bundle_path: Path, username: str):
    """Copy bundle to git backup repo and commit+push. Non-blocking."""
    if not BACKUP_REPO_URL:
        return
    threading.Thread(target=_do_backup, args=(bundle_path, username), daemon=True).start()


def _do_backup(bundle_path: Path, username: str):
    with _lock:
        try:
            import shutil
            repo = _get_repo()
            if repo is None:
                return

            # Mirror the same relative path inside the backup repo
            rel = bundle_path.relative_to(Path(os.environ.get("SYNC_DATA_DIR", "/data")) / "sessions")
            dest = BACKUP_REPO_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle_path, dest)

            repo.index.add([str(dest.relative_to(BACKUP_REPO_DIR))])
            repo.index.commit(f"backup: {username}/{bundle_path.name}")
            repo.remotes.origin.push()
        except Exception as e:
            # Never crash the main server for a backup failure
            print(f"[git-backup] WARNING: {e}")
