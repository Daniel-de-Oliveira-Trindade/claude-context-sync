"""
HooksManager - Installs and removes Claude Code lifecycle hooks

Reads and writes ~/.claude/settings.json to configure SessionEnd and SessionStart
hooks that automatically run sync-push and sync-pull.

Hook identifier: all hooks added by this tool contain "claude-context-sync" in the
command string, which is used to detect and remove them without touching other hooks.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

HOOK_MARKER = "claude-context-sync"


def _resolve_executable() -> str:
    """
    Return the absolute path to the claude-sync executable.

    Uses the same Python Scripts directory as the currently running interpreter,
    so the hook works even when the Scripts dir is not in the system PATH.
    """
    scripts_dir = Path(sys.executable).parent / "Scripts"
    for name in ("claude-sync.exe", "claude-sync"):
        candidate = scripts_dir / name
        if candidate.exists():
            return str(candidate)
    # Fallback: rely on PATH (may fail if not configured)
    return "claude-sync"


def _build_hooks() -> Dict[str, Any]:
    exe = _resolve_executable()
    return {
        "SessionEnd": {
            "hooks": [
                {
                    "type": "command",
                    "command": f"{exe} sync-push --session $CLAUDE_SESSION_ID --auto"
                }
            ]
        },
        "SessionStart": {
            "hooks": [
                {
                    "type": "command",
                    "command": f"{exe} sync-pull --latest --auto"
                }
            ]
        },
    }


class HooksManager:
    """Manages claude-context-sync hooks in ~/.claude/settings.json"""

    def _read_settings(self) -> Dict[str, Any]:
        """Read settings.json, returning empty dict if it doesn't exist."""
        if CLAUDE_SETTINGS.exists():
            with open(CLAUDE_SETTINGS, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _write_settings(self, settings: Dict[str, Any]) -> None:
        """Write settings.json, creating parent directories if needed."""
        CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        with open(CLAUDE_SETTINGS, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")

    def _backup_settings(self) -> Path:
        """Create a backup of settings.json before modifying it."""
        backup = CLAUDE_SETTINGS.with_suffix(".json.bak")
        if CLAUDE_SETTINGS.exists():
            shutil.copy2(CLAUDE_SETTINGS, backup)
        return backup

    def _hook_already_installed(self, event_hooks: list) -> bool:
        """Check if any hook in the list was added by claude-context-sync."""
        for hook_group in event_hooks:
            for hook in hook_group.get("hooks", []):
                if HOOK_MARKER in hook.get("command", ""):
                    return True
        return False

    def install(self, force: bool = False) -> Dict[str, str]:
        """
        Install SessionEnd and SessionStart hooks into ~/.claude/settings.json.

        Args:
            force: If True, remove existing claude-context-sync hooks and reinstall
                   the current version. If False (default), skip events that already
                   have a hook installed.

        Returns:
            Dict mapping event name to status: "installed", "already_installed", or "updated"
        """
        backup = self._backup_settings()
        settings = self._read_settings()

        if "hooks" not in settings:
            settings["hooks"] = {}

        results = {}
        hooks_to_install = _build_hooks()

        for event, hook_config in hooks_to_install.items():
            existing = settings["hooks"].get(event, [])

            if force:
                # Remove old claude-context-sync hooks, then add fresh version
                existing = [
                    g for g in existing
                    if not any(HOOK_MARKER in h.get("command", "") for h in g.get("hooks", []))
                ]
                settings["hooks"][event] = existing + [hook_config]
                results[event] = "updated"
            elif self._hook_already_installed(existing):
                results[event] = "already_installed"
            else:
                settings["hooks"][event] = existing + [hook_config]
                results[event] = "installed"

        self._write_settings(settings)
        return results

    def get_installed_commands(self) -> Dict[str, str]:
        """
        Return the command strings for currently installed claude-context-sync hooks.

        Returns:
            Dict mapping event name to command string, only for installed hooks.
            Example: {"SessionEnd": "claude-context-sync sync-push --session $CLAUDE_SESSION_ID --auto"}
        """
        settings = self._read_settings()
        result = {}
        for event in _build_hooks():
            for group in settings.get("hooks", {}).get(event, []):
                for hook in group.get("hooks", []):
                    cmd = hook.get("command", "")
                    if HOOK_MARKER in cmd:
                        result[event] = cmd
        return result

    def uninstall(self) -> Dict[str, str]:
        """
        Remove all hooks added by claude-context-sync from ~/.claude/settings.json.

        Returns:
            Dict mapping event name to status: "removed" or "not_found"
        """
        if not CLAUDE_SETTINGS.exists():
            return {event: "not_found" for event in _build_hooks()}

        self._backup_settings()
        settings = self._read_settings()

        if "hooks" not in settings:
            return {event: "not_found" for event in _build_hooks()}

        results = {}

        for event in _build_hooks():
            existing = settings["hooks"].get(event, [])
            filtered = [
                group for group in existing
                if not any(
                    HOOK_MARKER in hook.get("command", "")
                    for hook in group.get("hooks", [])
                )
            ]

            if len(filtered) < len(existing):
                settings["hooks"][event] = filtered
                results[event] = "removed"
            else:
                results[event] = "not_found"

            # Clean up empty event lists
            if not settings["hooks"][event]:
                del settings["hooks"][event]

        # Clean up empty hooks object
        if not settings["hooks"]:
            del settings["hooks"]

        self._write_settings(settings)
        return results

    def status(self) -> Dict[str, bool]:
        """
        Check whether hooks are currently installed.

        Returns:
            Dict mapping event name to True if installed, False otherwise
        """
        settings = self._read_settings()
        hooks = settings.get("hooks", {})

        result = {}
        for event in _build_hooks():
            existing = hooks.get(event, [])
            result[event] = self._hook_already_installed(existing)

        return result
