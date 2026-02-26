"""
GitSync - Synchronizes session bundles via a Git repository

Allows exporting sessions directly to a Git repo and importing them
from a Git repo on another device.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


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
        """
        Run a git command.

        Args:
            cmd: Command arguments list
            cwd: Working directory (default: local_dir)

        Returns:
            CompletedProcess with stdout/stderr

        Raises:
            subprocess.CalledProcessError: If the command fails
        """
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

    def ensure_repo(self):
        """
        Ensure the local repository exists and is up to date.
        Clones if it doesn't exist; pulls if it does and the remote has commits.

        Raises:
            subprocess.CalledProcessError: If git clone or pull fails
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

    def push_bundle(self, bundle_path: str, session_id: str, label: str = "") -> str:
        """
        Copy a bundle to the repository and commit + push.

        Args:
            bundle_path: Local bundle file path
            session_id: Session UUID (used in the commit message)
            label: Optional descriptive text to include in the commit message,
                   e.g. "my-app | Fix the authentication bug"

        Returns:
            Path to the bundle in the repository

        Raises:
            FileNotFoundError: If the bundle file does not exist
            subprocess.CalledProcessError: If a git command fails
        """
        src = Path(bundle_path)
        if not src.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")

        self.ensure_repo()

        dest = self.local_dir / src.name
        shutil.copy2(src, dest)

        commit_msg = f"sync: session {session_id[:8]}"
        if label:
            commit_msg += f" | {label}"

        self._run(["git", "add", dest.name])
        self._run(["git", "commit", "-m", commit_msg])
        self._run(["git", "push"])

        return str(dest)

    def pull_bundle(self, session_id_prefix: str) -> Optional[str]:
        """
        Pull the repository and find a bundle by session ID prefix.

        Args:
            session_id_prefix: Session UUID prefix (minimum 8 chars)

        Returns:
            Path to the found bundle, or None if not found
        """
        self.ensure_repo()

        for f in self.local_dir.iterdir():
            if f.is_file() and session_id_prefix in f.name and (
                f.suffix == '.bundle'
                or f.name.endswith('.bundle.gz')
                or f.name.endswith('.bundle.gz.enc')
            ):
                return str(f)

        return None

    def list_bundles(self) -> List[str]:
        """
        List all bundles available in the repository.

        Returns:
            Sorted list of bundle filenames (includes .bundle, .bundle.gz, .bundle.gz.enc)
        """
        self.ensure_repo()

        bundles = []
        for f in self.local_dir.iterdir():
            if f.is_file() and (
                f.suffix == '.bundle'
                or f.name.endswith('.bundle.gz')
                or f.name.endswith('.bundle.gz.enc')
            ):
                bundles.append(f.name)

        return sorted(bundles)

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
            # Get filenames added in each commit, most recent first
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
                if (
                    name.endswith('.bundle')
                    or name.endswith('.bundle.gz')
                    or name.endswith('.bundle.gz.enc')
                ):
                    candidate = self.local_dir / name
                    if candidate.exists():
                        return str(candidate)
        except subprocess.CalledProcessError:
            pass

        return None

    def get_bundle_labels(self) -> dict:
        """
        Read the Git log and return a dict mapping filename -> commit message.

        For each bundle, retrieves the message of the commit that added it,
        allowing descriptive labels to be shown in sync-list.

        Returns:
            Dict of {filename: commit_message}, e.g.:
            {"097f3474-....bundle.gz": "sync: session 097f3474 | my-app | Fix auth bug"}
        """
        self.ensure_repo()

        labels = {}
        try:
            # git log com formato: hash + subject, mostrando arquivos adicionados
            result = self._run([
                "git", "log",
                "--pretty=format:COMMIT:%s",
                "--name-only",
                "--diff-filter=A"
            ])
            current_msg = ""
            for line in result.stdout.splitlines():
                if line.startswith("COMMIT:"):
                    current_msg = line[7:]  # strip "COMMIT:" prefix
                elif line.strip() and not line.startswith("COMMIT:"):
                    filename = line.strip()
                    if filename and (
                        filename.endswith('.bundle')
                        or filename.endswith('.bundle.gz')
                        or filename.endswith('.bundle.gz.enc')
                    ):
                        labels[filename] = current_msg
        except subprocess.CalledProcessError:
            pass  # Empty repo or no commits — return empty dict

        return labels
