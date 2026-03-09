# Claude Context Sync

Sync your [Claude Code](https://claude.ai/code) sessions between machines via a private Git repository — without leaving VS Code.

## Features

- **Push sessions** — export the current Claude Code session and push to your Git repo
- **Pull sessions** — fetch a session from any machine and restore it locally
- **Local Sessions view** — browse all sessions grouped by project, with local backup history
- **Remote Bundles view** — see all sessions stored in your Git repo, pull any version
- **Restore backups** — roll back to any previous backup of a session by date

## Requirements

- [claude-context-sync CLI](https://github.com/YOUR_REPO) installed (`pip install claude-context-sync`)
- A private Git repository configured as your sync target (`claude-sync repo <url>`)

## Getting Started

1. Install the CLI: `pip install claude-context-sync`
2. Configure your Git repo: `claude-sync repo git@github.com:you/sessions.git`
3. Open VS Code — the extension auto-detects the CLI and loads your sessions

## Extension Settings

| Setting | Default | Description |
|---|---|---|
| `claudeContextSync.cliPath` | *(auto)* | Path to `claude-sync` executable. Leave empty for auto-detection. |
| `claudeContextSync.autoRefreshOnFocus` | `true` | Refresh local sessions when panel gains focus |
| `claudeContextSync.autoFetchRemoteOnFocus` | `false` | Pull from Git when panel gains focus (disable on slow connections) |

## Commands

- **Claude Sync: Push Session** — push current session to Git
- **Claude Sync: Pull Session** — pull a session from Git
- **Claude Sync: Restore Backup** — restore a local backup by date
- **Claude Sync: Refresh Local Sessions** — reload local session list
- **Claude Sync: Refresh Remote Bundles** — git pull + reload remote list
- **Claude Sync: Show Output Log** — open the output channel for debugging

## Notes

This extension requires the `claude-context-sync` Python CLI to be installed. Sessions are stored as encrypted or plain bundles in a Git repository you control — no cloud service involved.
