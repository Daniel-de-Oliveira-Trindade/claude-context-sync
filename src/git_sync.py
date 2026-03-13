"""
GitSync - Synchronizes session bundles via a Git repository

Allows exporting sessions directly to a Git repo and importing them
from a Git repo on another device.

v0.5.0: Bundles are organized in per-project subfolders inside the repo.
        Local backups are saved to ~/.claude-sync-git/backups/ (never committed).
"""

import gzip
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def sanitize_project_name(name: str) -> str:
    """
    Convert a project name into a safe folder name.

    Rules:
    - lowercase
    - spaces → hyphens
    - keep only a-z, 0-9, hyphen, underscore
    - strip leading/trailing hyphens/underscores
    - empty result → "sem-projeto"

    Examples:
        "My App"              → "my-app"
        "claude-session-sync" → "claude-session-sync"
        "Projeto! Final"      → "projeto-final"
        ""                    → "sem-projeto"
    """
    name = name.lower().strip()
    name = name.replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-_]", "", name)
    name = name.strip("-_")
    return name or "sem-projeto"


# Regex helpers used by multiple methods
_UUID_RE = re.compile(
    r'([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I
)
_TS_RE = re.compile(r'(\d{8}-\d{6})')


def _is_bundle(name: str) -> bool:
    """Return True if the filename looks like a session bundle."""
    return (
        name.endswith(".bundle")
        or name.endswith(".bundle.gz")
        or name.endswith(".bundle.gz.enc")
    )


class GitSync:
    """Manages bundle synchronization via a Git repository"""

    def __init__(self, repo_url: str, local_dir: Optional[str] = None):
        """
        Initialize GitSync.

        Args:
            repo_url: Git repository URL (SSH or HTTPS)
            local_dir: Local directory for the repo clone (default: ~/.claude-sync-git)
        """
        self.repo_url = repo_url
        self.local_dir = Path(local_dir) if local_dir else Path.home() / ".claude-sync-git"

    def _run(self, cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or self.local_dir,
            check=True
        )

    def _has_remote_commits(self) -> bool:
        """Check whether the remote has any commits (i.e., the repo is not empty)."""
        try:
            result = self._run(["git", "ls-remote", "--heads", "origin"])
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def _ensure_gitignore(self) -> None:
        """
        Ensure that backups/ is listed in .gitignore inside the sync repo.
        Creates .gitignore if it doesn't exist; appends the entry if missing.
        Commits and pushes the change so it propagates to other machines.
        """
        gitignore = self.local_dir / ".gitignore"
        entry = "backups/"

        if gitignore.exists():
            current_lines = gitignore.read_text(encoding="utf-8").splitlines()
            if entry in current_lines:
                return
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write(f"\n{entry}\n")
        else:
            gitignore.write_text(f"{entry}\n", encoding="utf-8")

        try:
            self._run(["git", "add", ".gitignore"])
            self._run(["git", "commit", "-m", "chore: add backups/ to .gitignore"])
            self._run(["git", "push"])
        except subprocess.CalledProcessError:
            pass  # Nothing to commit, or push failed — not critical

    def ensure_repo(self):
        """
        Ensure the local repository exists and is up to date.
        Clones if it doesn't exist; pulls if it does and the remote has commits.
        Also ensures backups/ is in .gitignore.
        """
        git_dir = self.local_dir / ".git"

        if not git_dir.exists():
            self.local_dir.mkdir(parents=True, exist_ok=True)
            print(f"Cloning repository to {self.local_dir}...")
            self._run(["git", "clone", self.repo_url, str(self.local_dir)], cwd=Path.home())
        else:
            if self._has_remote_commits():
                print(f"Updating local repository at {self.local_dir}...")
                self._run(["git", "pull", "--rebase"])
            else:
                print(f"Repository ready at {self.local_dir} (empty remote, skipping pull)")

        self._ensure_gitignore()

    def push_bundle(
        self,
        bundle_path: str,
        session_id: str,
        label: str = "",
        project_name: str = ""
    ) -> str:
        """
        Copy a bundle to the repository (in a per-project subfolder) and commit + push.

        On the first push for a session, any old flat-root bundles with the same
        session_id are lazily migrated into the project subfolder in the same commit.

        Args:
            bundle_path: Local bundle file path
            session_id: Session UUID (used in the commit message)
            label: Optional descriptive text for the commit message
            project_name: Human-readable project name (will be sanitized into a folder name)

        Returns:
            Absolute path to the bundle in the repository
        """
        src = Path(bundle_path)
        if not src.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")

        self.ensure_repo()

        folder = sanitize_project_name(project_name) if project_name else "sem-projeto"
        dest_dir = self.local_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / src.name
        shutil.copy2(src, dest)

        # Files to stage with plain git add (new/untracked files)
        files_to_add = [f"{folder}/{src.name}"]

        # Lazy migration: move old flat-root bundles for this session into the project folder
        for old_file in list(self.local_dir.iterdir()):
            if not old_file.is_file():
                continue
            if not _is_bundle(old_file.name):
                continue
            if session_id[:8] not in old_file.name and session_id not in old_file.name:
                continue
            # Don't move the file we just copied
            if old_file.name == src.name and old_file.parent == dest_dir:
                continue

            new_loc = dest_dir / old_file.name
            rel_old = old_file.name
            rel_new = f"{folder}/{old_file.name}"
            try:
                # git mv handles the rename atomically in the index
                self._run(["git", "mv", rel_old, rel_new])
            except subprocess.CalledProcessError:
                # File not tracked by git yet — move manually and add
                shutil.move(str(old_file), new_loc)
                files_to_add.append(rel_new)

        commit_msg = f"sync: session {session_id[:8]}"
        if label:
            commit_msg += f" | {label}"

        self._run(["git", "add", "--"] + files_to_add)
        self._run(["git", "commit", "-m", commit_msg])
        self._run(["git", "push"])

        return str(dest)

    def pull_bundle(self, session_id_prefix: str) -> Optional[str]:
        """
        Pull the repository and find a bundle by session ID prefix.

        Searches project subfolders first, then the flat root for backward
        compatibility with bundles pushed before v0.5.0.

        Args:
            session_id_prefix: Session UUID prefix (minimum 8 chars)

        Returns:
            Absolute path to the found bundle, or None if not found
        """
        self.ensure_repo()

        # Search project subfolders first (v0.5.0+ structure)
        for subdir in self.local_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith(".") or subdir.name == "backups":
                continue
            for f in subdir.iterdir():
                if f.is_file() and session_id_prefix in f.name and _is_bundle(f.name):
                    return str(f)

        # Backward compat: search flat root (pre-v0.5.0 bundles)
        for f in self.local_dir.iterdir():
            if f.is_file() and session_id_prefix in f.name and _is_bundle(f.name):
                return str(f)

        return None

    def pull_bundle_by_filename(self, filename: str) -> Optional[str]:
        """Find a bundle by its exact filename (searches project subfolders then root)."""
        self.ensure_repo()

        for subdir in self.local_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith(".") or subdir.name == "backups":
                continue
            candidate = subdir / filename
            if candidate.is_file():
                return str(candidate)

        # Backward compat: flat root
        candidate = self.local_dir / filename
        if candidate.is_file():
            return str(candidate)

        return None

    def list_bundles(self) -> List[Dict]:
        """
        List all bundles available in the repository.

        Returns a list of dicts (one per bundle file) with fields:
            path            - absolute path to the file
            relative        - path relative to local_dir
            filename        - basename only
            project_folder  - subfolder name, "" if in the flat root
            session_id_prefix - first 8 hex chars of the UUID in the filename
            timestamp       - "YYYYMMDD-HHMMSS" or "" if not present

        Sorted by (project_folder, session_id_prefix, timestamp).
        """
        self.ensure_repo()

        bundles = []

        def _make_entry(f: Path, project_folder: str) -> None:
            if not _is_bundle(f.name):
                return
            uuid_match = _UUID_RE.search(f.name)
            ts_match = _TS_RE.search(f.name)
            bundles.append({
                "path": str(f),
                "relative": str(f.relative_to(self.local_dir)).replace("\\", "/"),
                "filename": f.name,
                "project_folder": project_folder,
                "session_id_prefix": uuid_match.group(1)[:8] if uuid_match else f.name[:8],
                "timestamp": ts_match.group(1) if ts_match else "",
            })

        # Flat root (backward compat)
        for f in self.local_dir.iterdir():
            if f.is_file():
                _make_entry(f, "")

        # Project subfolders
        for subdir in self.local_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith(".") or subdir.name == "backups":
                continue
            for f in subdir.iterdir():
                if f.is_file():
                    _make_entry(f, subdir.name)

        return sorted(bundles, key=lambda b: (b["project_folder"], b["session_id_prefix"], b["timestamp"]))

    def get_latest_bundle(self) -> Optional[str]:
        """
        Return the path to the most recently pushed bundle, based on Git commit order.

        Used by sync-pull --latest (SessionStart hook): pulls only the newest bundle
        so the user gets the latest session from another machine without interaction.

        Returns:
            Absolute path to the most recent bundle file, or None if the repo is empty.
        """
        self.ensure_repo()

        try:
            result = self._run([
                "git", "log",
                "--pretty=format:",
                "--name-only",
                "--diff-filter=A"
            ])
            for line in result.stdout.splitlines():
                name = line.strip()
                if not name:
                    continue
                if _is_bundle(name):
                    # name may be "project-folder/filename.bundle.gz" — Path handles it
                    candidate = self.local_dir / name
                    if candidate.exists():
                        return str(candidate)
        except subprocess.CalledProcessError:
            pass

        return None

    def get_bundle_labels(self) -> dict:
        """
        Read the Git log and return a dict mapping relative_path -> commit message.

        Keys are the relative paths returned by git log (e.g.
        "claude-session-sync/097f3474_....bundle.gz"), matching the "relative"
        field from list_bundles().

        Returns:
            Dict of {relative_path: commit_message}
        """
        self.ensure_repo()

        labels = {}
        try:
            result = self._run([
                "git", "log",
                "--pretty=format:COMMIT:%s",
                "--name-only",
                "--diff-filter=A"
            ])
            current_msg = ""
            for line in result.stdout.splitlines():
                if line.startswith("COMMIT:"):
                    current_msg = line[7:]
                elif line.strip():
                    relative = line.strip().replace("\\", "/")
                    filename = relative.split("/")[-1]
                    if _is_bundle(filename):
                        labels[relative] = current_msg
                        # Also index by bare filename for backward compat
                        labels[filename] = current_msg
        except subprocess.CalledProcessError:
            pass

        return labels

    def save_local_backup(
        self,
        bundle_path: str,
        session_id_prefix: str,
        project_name: str = ""
    ) -> str:
        """
        Save a local backup of the bundle to ~/.claude-sync-git/backups/{project}/.

        Backups are never committed to git (backups/ is in .gitignore).
        Always saves as .gz (compresses plain .bundle files on the fly).

        Args:
            bundle_path: Absolute path to the bundle file (decrypted)
            session_id_prefix: First 8 chars of the session UUID (used in filename)
            project_name: Human-readable project name (will be sanitized)

        Returns:
            Absolute path to the saved backup, or "" if saving was not possible
        """
        src = Path(bundle_path)
        if not src.exists():
            return ""

        # Skip encrypted files — backup only decrypted content
        if src.name.endswith(".enc"):
            return ""

        folder = sanitize_project_name(project_name) if project_name else "sem-projeto"
        backup_dir = self.local_dir / "backups" / folder
        backup_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{session_id_prefix}_{ts}.bundle.gz"
        backup_path = backup_dir / backup_name

        try:
            if src.name.endswith(".bundle.gz"):
                shutil.copy2(src, backup_path)
            else:
                # Plain .bundle → compress
                with open(src, "rb") as f_in:
                    with gzip.open(backup_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
        except Exception:
            return ""

        return str(backup_path)
