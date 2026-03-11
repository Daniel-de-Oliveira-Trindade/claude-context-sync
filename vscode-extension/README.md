# Claude Context Sync

Sync your [Claude Code](https://claude.ai/code) sessions between machines via a private Git repository — without leaving VS Code.

## Features

- **Push sessions** — export the current Claude Code session and push to your Git repo
- **Pull sessions** — fetch a session from any machine and restore it locally, with project-mismatch detection
- **Local Sessions view** — browse all sessions grouped by project, including sessions that were never indexed
- **Remote Bundles view** — see all sessions stored in your Git repo, pull any version
- **Restore backups** — roll back to any previous backup of a session by date

## Requirements

- Git installed on your machine
- A private Git repository configured as your sync target

No Python installation needed — the CLI is bundled inside the extension.

## Getting Started

1. Install the extension from the VS Code Marketplace
2. Configure your Git repo: open the Command Palette → **Claude Sync: Set Repository URL**
3. The extension auto-detects your sessions and loads them immediately

## Extension Settings

| Setting | Default | Description |
|---|---|---|
| `claudeContextSync.cliPath` | *(auto)* | Path to `claude-sync` executable. Leave empty to use the bundled binary. |
| `claudeContextSync.autoRefreshOnFocus` | `true` | Refresh local sessions when the panel gains focus. Set to `false` if you prefer to refresh manually. |
| `claudeContextSync.autoFetchRemoteOnFocus` | `false` | Pull from Git when the panel gains focus. Disable on slow connections — use the ↺ button instead. |

## Commands

| Command | Description |
|---|---|
| **Claude Sync: Push Session** | Export the current session to Git |
| **Claude Sync: Pull Session** | Pull a session from Git (with project-mismatch detection) |
| **Claude Sync: Restore Backup** | Restore a local backup by date |
| **Claude Sync: Refresh Local Sessions** | Reload the local session list |
| **Claude Sync: Refresh Remote Bundles** | Git pull + reload the remote list |
| **Claude Sync: Install Auto-Sync Hooks** | Install SessionEnd/SessionStart hooks in Claude Code |
| **Claude Sync: Set Repository URL** | Set the default Git repository for sync |
| **Claude Sync: Show Output Log** | Open the output channel for debugging |

## How Pull Works

When you pull a remote session, the extension checks whether the session belongs to the same project as the currently open workspace folder. If they don't match, you are prompted to:

- **Use the current folder** — import into the open workspace (you know what you're doing)
- **Choose a folder** — browse to the correct project directory
- **Import anyway** — force import without validation

After pulling, the session is available in Claude Code when you open the matching project folder.

## How Restore Backup Works

Restoring a backup always restores the session to its **original project folder** (the path stored inside the bundle). After restoring, open that folder in Claude Code to resume the session.

## Local Sessions Discovery

Sessions are discovered by scanning `~/.claude/projects/` directly, so they appear even if they were never indexed by Claude Code's `sessions-index.json`. This means sessions from projects that are not Git repositories (or that were never synced) are also visible.

## Changelog

### 0.5.1
- **Fix**: Local Sessions now shows sessions from all projects, including those not indexed by Claude Code (`sessions-index.json` fallback to direct `.jsonl` scan)
- **Fix**: Project names now decoded correctly from encoded directory names (`claude-session-sync` instead of `sync`, `cadeeu` instead of just the last segment)
- **Fix**: `sync-push` now correctly detects project name for sessions without index metadata — no more `sem-projeto` labels
- **New**: Pull command now detects project mismatches — warns when the selected bundle belongs to a different project than the open workspace, and offers to choose the correct folder
- **New**: Pull and Restore messages now clearly state which project folder the session was imported into
- **New**: Bundled CLI binary — no Python installation required

### 0.1.0
- Initial release: push/pull, local sessions, remote bundles, backup/restore, auto-sync hooks
