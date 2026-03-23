# Claude Context Sync

Sync your [Claude Code](https://claude.ai/code) sessions between machines via a private Git repository — without leaving VS Code.

## Features

- **Push sessions** — export the current Claude Code session and push to your Git repo or central server
- **Pull sessions** — fetch a session from any machine and restore it locally, with project-mismatch detection
- **Local Sessions view** — browse all sessions grouped by project, including sessions that were never indexed
- **Remote Bundles view** — see all sessions stored in your Git repo or central server, pull any version
- **Restore backups** — roll back to any previous backup of a session by date
- **Auto Sync** — toggle the file watcher daemon directly from the sidebar; status bar shows current state
- **Server Mode** — connect to a central HTTP server instead of (or in addition to) Git

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
| `claudeContextSync.serverUrl` | *(empty)* | URL of the central sync server. When set, push/pull/list use HTTP instead of Git. |
| `claudeContextSync.serverToken` | *(empty)* | Access token for the central server. Synced to the CLI automatically on activation. |
| `claudeContextSync.autoSync` | `false` | Start the file watcher daemon automatically when VS Code opens. |

## Commands

| Command | Description |
|---|---|
| **Claude Sync: Push Session** | Export the current session to Git or central server |
| **Claude Sync: Pull Session** | Pull a session (with project-mismatch detection) |
| **Claude Sync: Restore Backup** | Restore a local backup by date |
| **Claude Sync: Refresh Local Sessions** | Reload the local session list |
| **Claude Sync: Refresh Remote Bundles** | Pull from remote + reload the remote list |
| **Claude Sync: Install Auto-Sync Hooks** | Install SessionEnd/SessionStart hooks in Claude Code |
| **Claude Sync: Set Repository URL** | Set the default Git repository for sync |
| **Claude Sync: Toggle Auto Sync** | Start or stop the file watcher daemon |
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

## Auto Sync

Auto Sync starts a background file watcher daemon that pushes sessions automatically whenever they change in `~/.claude/projects/`.

**To toggle Auto Sync:**
- Click the $(radio-tower) button in the **Local Sessions** toolbar, or
- Click the **Auto Sync: ON / OFF** item in the status bar, or
- Set `claudeContextSync.autoSync: true` in Settings to start it automatically on VS Code launch.

The daemon uses a 30-second debounce — it waits until the session has been idle for 30 seconds before pushing, so it doesn't push on every keystroke.

## Server Mode

When `claudeContextSync.serverUrl` is configured, the extension syncs `serverUrl` and `serverToken` to the CLI automatically on activation. Push, pull, and list operations then use HTTP instead of Git.

To set up:
1. Open Settings (`Ctrl+,`) → search `claudeContextSync`
2. Set **Server URL** to your server address (e.g., `https://sync.example.com`)
3. Set **Server Token** to your access token (obtained from your administrator)

The extension restarts the watcher daemon on activation if `autoSync` was previously ON, so sync resumes automatically after VS Code restarts.

## Changelog

### 0.6.0
- **New**: Auto Sync toggle button ($(radio-tower)) in the Local Sessions toolbar — starts/stops the file watcher daemon
- **New**: Status bar item "Auto Sync: ON / OFF" (clickable)
- **New**: `claudeContextSync.serverUrl` setting — central server URL for HTTP-based sync
- **New**: `claudeContextSync.serverToken` setting — access token, synced to CLI on activation
- **New**: `claudeContextSync.autoSync` setting — start watcher daemon automatically on launch
- **New**: On activation, `serverUrl` and `serverToken` are pushed to the CLI config automatically
- **New**: Watcher daemon is restarted on activation if `autoSync` was previously ON

### 0.5.1
- **Fix**: Local Sessions now shows sessions from all projects, including those not indexed by Claude Code (`sessions-index.json` fallback to direct `.jsonl` scan)
- **Fix**: Project names now decoded correctly from encoded directory names (`claude-session-sync` instead of `sync`, `cadeeu` instead of just the last segment)
- **Fix**: `sync-push` now correctly detects project name for sessions without index metadata — no more `sem-projeto` labels
- **New**: Pull command now detects project mismatches — warns when the selected bundle belongs to a different project than the open workspace, and offers to choose the correct folder
- **New**: Pull and Restore messages now clearly state which project folder the session was imported into
- **New**: Bundled CLI binary — no Python installation required

### 0.1.0
- Initial release: push/pull, local sessions, remote bundles, backup/restore, auto-sync hooks
