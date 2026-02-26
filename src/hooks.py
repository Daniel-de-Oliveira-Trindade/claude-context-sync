"""
HooksManager - Installs and removes Claude Code lifecycle hooks

Reads and writes ~/.claude/settings.json to configure SessionEnd and SessionStart
hooks that automatically run sync-push and sync-pull.

Hook identifier: all hooks added by this tool contain "claude-context-sync" in the
command string, which is used to detect and remove them without touching other hooks.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Dict

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

HOOK_MARKER = "claude-context-sync"

HOOKS_TO_INSTALL = {
    "SessionEnd": {
        "hooks": [
            {
                "type": "command",
                "command": "claude-context-sync sync-push --session $CLAUDE_SESSION_ID --auto"
            }
        ]
    },
    "SessionStart": {
        "hooks": [
            {
                "type": "command",
                "command": "claude-context-sync sync-pull --latest --auto"
            }
        ]
    }
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

    def install(self) -> Dict[str, str]:
        """
        Install SessionEnd and SessionStart hooks into ~/.claude/settings.json.

        Returns:
            Dict mapping event name to status: "installed" or "already_installed"
        """
        backup = self._backup_settings()
        settings = self._read_settings()

        if "hooks" not in settings:
            settings["hooks"] = {}

        results = {}

        for event, hook_config in HOOKS_TO_INSTALL.items():
            existing = settings["hooks"].get(event, [])

            if self._hook_already_installed(existing):
                results[event] = "already_installed"
            else:
                settings["hooks"][event] = existing + [hook_config]
                results[event] = "installed"

        self._write_settings(settings)
        return results

    def uninstall(self) -> Dict[str, str]:
        """
        Remove all hooks added by claude-context-sync from ~/.claude/settings.json.

        Returns:
            Dict mapping event name to status: "removed" or "not_found"
        """
        if not CLAUDE_SETTINGS.exists():
            return {event: "not_found" for event in HOOKS_TO_INSTALL}

        self._backup_settings()
        settings = self._read_settings()

        if "hooks" not in settings:
            return {event: "not_found" for event in HOOKS_TO_INSTALL}

        results = {}

        for event in HOOKS_TO_INSTALL:
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
        for event in HOOKS_TO_INSTALL:
            existing = hooks.get(event, [])
            result[event] = self._hook_already_installed(existing)

        return result
