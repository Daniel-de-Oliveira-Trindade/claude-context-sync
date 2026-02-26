# Claude Context Sync

> Transfer your Claude Code sessions between different devices seamlessly

## Overview

**Claude Context Sync** is a CLI tool that exports and imports Claude Code sessions between devices. It solves the problem of absolute path differences between machines using a smart path-transformation system.

**Current version: 0.4.0**

**Features:**
- Full session transfer: messages, file-history, and todos
- Automatic path transformation between devices (no manual editing)
- gzip compression (`--compress`) — reduces bundle size by up to 86%
- Automatic progress bars for large sessions
- Git-based sync via private repository (`sync-push` / `sync-pull`)
- Interactive session picker — no need to copy/paste UUIDs
- Descriptive Git commit labels (project name + first prompt)
- SHA256 integrity validation
- Backwards-compatible with older bundles (v1.0.0)
- **Automatic sync hooks** — SessionEnd/SessionStart integration with Claude Code (`hooks-install`)
- **Optional AES-256-GCM encryption** — passphrase-based, no raw key files to manage (`--encrypt`)
- **Structured logs** — `hook.log` for automatic sync, `--verbose` for manual commands

> **Platform support:** Fully tested on Windows. Linux and macOS support is planned — it likely works already with minor adaptations. Community testing welcome!

## The Problem

When working across two different PCs, you constantly lose your Claude Code conversation context because:
- Absolute paths differ between machines (`C:\Users\alice\...` vs `D:\Projects\...`)
- Directory structures vary between devices
- There is no native way to transfer the full conversation history

**This tool solves all of that.**

---

## Installation

### Prerequisites
- Python 3.8+
- Git (for Git-based sync)

### Install the package

```bash
# Clone the repository
git clone https://github.com/<your-username>/claude-context-sync.git
cd claude-context-sync

# Install pip if needed
python -m ensurepip --upgrade

# Install the package
python -m pip install -e .
```

This installs the `claude-sync` command globally on your system.

---

## Key Concepts

### Session ID

Every Claude Code conversation has a unique **session ID** — a UUID that never changes:

```
097f3474-8974-4405-98c0-b70d4bf920d5
```

Use `claude-sync list` to see your session IDs. Because the ID never changes, you can always use it to sync the same conversation across devices.

### Devices

Each PC needs to be configured once with `claude-sync config`, telling the tool where your projects live on that device. The tool uses this to automatically convert paths during export and import.

---

## Full Workflow — First Time

### On the main PC

**1. Configure the device:**

```bash
claude-sync config --device-id desktop --projects-path "C:/Users/<username>/Documents/projects" --set-current
```

**2. List your sessions:**

```bash
claude-sync list
```

Output:
```
Found 3 session(s):

Session ID: 097f3474-8974-4405-98c0-b70d4bf920d5
  First prompt: Fix the authentication bug in login
  Messages: 1504
  Created: 2026-01-15T10:00:00.000Z
  Modified: 2026-02-19T18:42:40.303Z
  Project: c--users-alice-documents-projects-my-app

Session ID: bedcc029-db4a-4474-a179-10ff88888ef0
  First prompt: Implement dashboard main page
  Messages: 312
  ...
```

**3. Set a default repository (once per device):**

```bash
claude-sync repo git@github.com:your-username/claude-sessions.git
# [OK] Default repository set to: git@github.com:your-username/claude-sessions.git
#      You can now run sync-push/pull/list without --repo
```

**4. Push a session to Git:**

From inside the project folder, run `sync-push` without any arguments to pick interactively:

```bash
cd C:/Users/<username>/Documents/projects/my-app
claude-sync sync-push --compress
```

Output:
```
Sessions in current project (my-app):

  [1] 097f3474  2026-02-20  Fix the authentication bug in login
  [2] bedcc029  2026-02-18  Implement dashboard main page

Choose session number: 1

Exporting session: 097f3474-8974-4405-98c0-b70d4bf920d5

Reading messages: 100%|##########| 1504/1504 [00:00<00:00]
Read 1504 messages from session
Normalizing paths: 100%|##########| 1504/1504 [00:00<00:00]
Exporting file-history and todos...
[OK] Exported 1504 messages to 097f3474-8974-4405-98c0-b70d4bf920d5.bundle.gz (compressed)
   Checksum: b77d1ef4...
   File-history: 36 entries
   Todos: 4 items

Pushing to Git repository: git@github.com:...
[OK] Bundle pushed to repository: 097f3474-8974-4405-98c0-b70d4bf920d5.bundle.gz

[SUCCESS] Session synced to Git successfully!

On another device, run:
  claude-sync sync-pull
```

### On the second PC

**5. Install claude-context-sync** (same steps as the Installation section above)

**6. Configure the device:**

```bash
claude-sync config --device-id laptop --projects-path "D:/Projects" --set-current
```

**7. Set the default repository (once per device):**

```bash
claude-sync repo git@github.com:your-username/claude-sessions.git
```

**8. Pull interactively — no need to know the session ID:**

```bash
claude-sync sync-pull
```

Output:
```
Pulling from Git repository: git@github.com:...
Using project path: D:/Projects/my-app
  (use --project-path to change)

Available bundles in repository:

  [1] 097f3474  my-app | Fix the authentication bug in login
  [2] bedcc029  my-app | Implement dashboard main page

Choose session number: 1

[OK] Found bundle: 097f3474-8974-4405-98c0-b70d4bf920d5.bundle.gz

[OK] Bundle validation passed
Denormalizing paths: 100%|##########| 1504/1504 [00:00<00:00]
Target project path: D:\Projects\my-app
[OK] Wrote 1504 messages
[OK] Restored 36 file-history entries
[OK] Restored 4 todo items
[OK] Updated sessions index

[SUCCESS] Session '097f3474...' imported successfully!
```

**9. Resume in Claude Code:**

Open Claude Code **inside the corresponding project folder** and use `/resume` to select the imported session.

---

## Updating an Existing Session

Because the session ID never changes, syncing the latest state of a conversation is always the same command:

```bash
# PC 1 — update the bundle in the repo with the latest messages
claude-sync sync-push --compress

# PC 2 — pull the updated version (use --force since the session already exists locally)
claude-sync sync-pull --force
```

---

## Multiple Projects in One Repository

You can use **a single Git repository** for all your sessions. Each bundle is named with the session ID, so there are no collisions:

```bash
# Set the repo once
claude-sync repo git@github.com:user/sessions.git

# Push sessions from different projects to the same repo
cd C:/projects/my-app && claude-sync sync-push --compress
cd C:/projects/api-server && claude-sync sync-push --compress
cd C:/projects/frontend && claude-sync sync-push --compress

# On the other PC, see all available sessions with labels
claude-sync sync-list

# Pull only the one you need
claude-sync sync-pull
```

---

## Alternative: Manual Transfer (No Git)

If you prefer not to use Git, transfer the bundle directly via USB, Google Drive, etc.:

```bash
# PC 1 — export to a file
claude-sync export 097f3474-8974-4405-98c0-b70d4bf920d5 \
  --output my-session.bundle \
  --compress

# Copy my-session.bundle.gz to the other PC via USB, Drive, etc.

# PC 2 — import the received file
claude-sync import my-session.bundle.gz
```

---

## Git Setup

To use Git-based sync, you need a private repository with authenticated access.

### 1. Create a private GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. Give it a name (e.g., `claude-sessions`)
3. Set it as **Private**
4. Click **Create repository** — leave it empty, no README

Repeat the authentication setup below on **each PC** you use.

---

### 2. Authenticate via SSH (recommended)

#### Step 1 — Check if you already have an SSH key

```bash
ls ~/.ssh/id_ed25519.pub
```

If the file exists, skip to Step 3.

#### Step 2 — Create the .ssh folder and generate a key

On Windows, the `.ssh` folder may not exist yet. Create it first:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "this-pc-name" -f ~/.ssh/id_ed25519 -N ""
```

> Replace `this-pc-name` with something that identifies the device, e.g., `desktop`, `work-laptop`.

#### Step 3 — Add GitHub to known hosts

Required on Windows — without this the connection fails with `Host key verification failed`:

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
```

#### Step 4 — Add the public key to GitHub

```bash
# Copy the output of this command
cat ~/.ssh/id_ed25519.pub
```

1. Go to [github.com/settings/ssh/new](https://github.com/settings/ssh/new)
2. **Title:** a name that identifies this PC (e.g., `home-laptop`)
3. **Key:** paste the key copied above
4. Click **Add SSH key**

#### Step 5 — Test the connection

```bash
ssh -T git@github.com
# Expected: Hi your-username! You've successfully authenticated...
```

If you see `Permission denied (publickey)`, the key was not added correctly — redo Step 4.

If you see `Host key verification failed`, redo Step 3.

---

### Alternative: Authenticate via HTTPS token

If you prefer not to configure SSH, use HTTPS with a Personal Access Token:

1. Generate a token at: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Required scopes: check **repo**

```bash
claude-sync sync-push \
  --repo https://your-username:YOUR_TOKEN@github.com/your-username/claude-sessions.git \
  --compress
```

> The token appears in the URL — do not share this command with anyone.

---

## Command Reference

### `claude-sync config`

Configure path mappings for a device. Run once per device.

```bash
claude-sync config --device-id DEVICE_ID --projects-path PATH [OPTIONS]
```

| Option | Description |
|---|---|
| `--device-id` | Device identifier (e.g., desktop, laptop) — required |
| `--projects-path` | Path to your projects folder — required |
| `--user` | Windows username (default: current user) |
| `--home` | Home directory (default: current home) |
| `--claude-dir` | .claude directory path (default: ~/.claude) |
| `--set-current` | Set this device as the current one |

```bash
# Windows
claude-sync config --device-id desktop --projects-path "C:/Users/<username>/Documents/projects" --set-current

# Linux / macOS
claude-sync config --device-id laptop --projects-path "/home/<username>/projects" --set-current
```

---

### `claude-sync list`

List all sessions available in the local Claude Code installation.

```bash
claude-sync list [--project PATH] [--limit N]
```

```bash
claude-sync list
claude-sync list --limit 50
claude-sync list --project "C:/Users/<username>/Documents/projects/my-app"
```

---

### `claude-sync export`

Export a session to a local bundle file.

```bash
claude-sync export SESSION_ID [--output PATH] [--compress]
```

| Option | Description |
|---|---|
| `--output` | Output file path (default: session.bundle) |
| `--compress` | Compress with gzip — recommended, reduces size by ~86% |

```bash
claude-sync export 097f3474-8974-4405-98c0-b70d4bf920d5
claude-sync export 097f3474-8974-4405-98c0-b70d4bf920d5 --output ~/Desktop/session.bundle --compress
```

---

### `claude-sync import`

Import a session from a bundle file. Supports both `.bundle` and `.bundle.gz` automatically.

```bash
claude-sync import BUNDLE_PATH [--force]
```

```bash
claude-sync import session.bundle
claude-sync import session.bundle.gz
claude-sync import session.bundle.gz --force   # overwrite if session already exists
```

---

### `claude-sync repo`

Set the default Git repository URL. Run once per device — after that, `sync-push`, `sync-pull`, and `sync-list` use it automatically without requiring `--repo`.

```bash
claude-sync repo URL
```

```bash
claude-sync repo git@github.com:your-username/claude-sessions.git
```

The URL is saved in `config/path_mappings.json` and can be overwritten at any time by running the command again. To use a different repo for a single command, pass `--repo URL` directly.

---

### `claude-sync sync-push`

Export a session and push it to the Git repository.

```bash
claude-sync sync-push [SESSION_ID] [--session UUID] [--repo URL] [--output NAME] [--compress] [--encrypt] [--auto] [--verbose]
```

| Option/Argument | Description |
|---|---|
| `SESSION_ID` | Session UUID (optional — if omitted, lists sessions in the current project) |
| `--session UUID` | Alternative to positional argument — useful for scripts and hooks |
| `--repo` | Git repository URL (optional if set with `claude-sync repo`) |
| `--output` | Bundle filename (default: `<session-id>.bundle`) |
| `--compress` | Compress with gzip |
| `--encrypt` | Encrypt bundle with AES-256-GCM (prompts for passphrase, or uses saved key) |
| `--auto` | Non-interactive mode for hooks — no prompts, errors logged to `hook.log` |
| `--verbose` | Write detailed steps to `~/.claude-context-sync/logs/app.log` |

**Without session ID — interactive picker from current project:**

```bash
cd C:/projects/my-app
claude-sync sync-push --compress
```

Output:
```
Sessions in current project (my-app):

  [1] 097f3474  2026-02-20  Fix the authentication bug in login
  [2] bedcc029  2026-02-18  Implement dashboard main page

Choose session number: 1
```

**With session ID — direct (no listing):**

```bash
claude-sync sync-push 097f3474-8974-4405-98c0-b70d4bf920d5 --compress
```

The Git commit generated includes the project name and first prompt as a description:
```
sync: session 097f3474 | my-app | Fix the authentication bug in login
```

---

### `claude-sync sync-pull`

Pull a bundle from the Git repository and import the session.

```bash
claude-sync sync-pull [SESSION_ID_PREFIX] [--repo URL] [--force] [--project-path PATH] [--latest] [--auto] [--verbose]
```

| Option/Argument | Description |
|---|---|
| `SESSION_ID_PREFIX` | First 8 chars of the session ID (optional — if omitted, lists bundles to choose from) |
| `--repo` | Git repository URL (optional if set with `claude-sync repo`) |
| `--force` | Overwrite the session if it already exists locally |
| `--project-path` | Local project path on this device (default: current directory) |
| `--latest` | Pull the most recently pushed bundle — used by `SessionStart` hooks |
| `--auto` | Non-interactive mode for hooks — no prompts, errors logged to `hook.log` |
| `--verbose` | Write detailed steps to `~/.claude-context-sync/logs/app.log` |

**Without session ID — interactive picker from remote repository:**

```bash
claude-sync sync-pull
```

Output:
```
Available bundles in repository:

  [1] 097f3474  my-app | Fix the authentication bug in login
  [2] bedcc029  my-app | Implement dashboard main page

Choose session number: 1
```

**With session ID prefix — direct (no listing):**

```bash
claude-sync sync-pull 097f3474
claude-sync sync-pull 097f3474 --force
claude-sync sync-pull 097f3474 --project-path "D:/Projects/my-app"
```

---

### `claude-sync sync-list`

List all bundles available in the Git repository, with their labels and IDs for use with `sync-pull`.

```bash
claude-sync sync-list [--repo URL]
```

```bash
claude-sync sync-list
# or with a specific repo:
claude-sync sync-list --repo git@github.com:user/another-repo.git
```

Output:
```
Found 3 bundle(s):

  097f3474-8974-4405-98c0-b70d4bf920d5.bundle.gz
    sync: session 097f3474 | my-app | Fix the authentication bug in login
    sync-pull ID: 097f3474

  bedcc029-db4a-4474-a179-10ff88888ef0.bundle.gz
    sync: session bedcc029 | api-server | Implement dashboard main page
    sync-pull ID: bedcc029

To import a bundle:
  claude-sync sync-pull <sync-pull ID>
```

---

### `claude-sync hooks-install`

Install automatic sync hooks in Claude Code. After running this command, sessions are pushed automatically when you close a conversation and pulled when you open Claude Code.

```bash
claude-sync hooks-install
```

This writes to `~/.claude/settings.json`:
- **SessionEnd** → runs `sync-push --session $CLAUDE_SESSION_ID --auto`
- **SessionStart** → runs `sync-pull --latest --auto`

A backup is saved to `~/.claude/settings.json.bak` before any changes.

Run `hooks-install` on each machine you want to sync automatically. It is **idempotent** — safe to run multiple times.

---

### `claude-sync hooks-uninstall`

Remove the automatic sync hooks from Claude Code settings. Does not affect other hooks.

```bash
claude-sync hooks-uninstall
```

---

### `claude-sync crypto-setup`

Configure an encryption passphrase for automatic encrypted sync.

```bash
claude-sync crypto-setup
```

The passphrase is used to derive an AES-256 key, which is saved locally at `~/.claude-context-sync/key`. Run this on every machine with the **same passphrase** — sessions encrypted on one machine can then be decrypted on the other automatically.

After setup:
- `sync-push --auto` will encrypt bundles automatically (no prompt)
- `sync-pull --auto` will decrypt them automatically (no prompt)

If you prefer to type the passphrase manually each time (without saving a key), just use `sync-push --encrypt` — it will prompt for the passphrase interactively.

---

### `claude-sync devices`

List configured devices.

```bash
claude-sync devices
```

---

### `claude-sync use`

Set the current device.

```bash
claude-sync use DEVICE_ID
```

```bash
claude-sync use laptop
claude-sync use desktop
```

---

## How It Works

### Path Transformation

The core problem is that absolute paths differ between devices:

| Device | Path |
|---|---|
| desktop | `C:\Users\alice\Documents\projects\my-app` |
| laptop | `D:\Projects\my-app` |

**Solution:** template variables that are resolved per device.

```
Export (desktop):  C:\Users\alice\Documents\projects\my-app
                   → ${PROJECTS}/my-app

Import (laptop):   ${PROJECTS}/my-app
                   → D:\Projects\my-app
```

### Bundle Format (v1.1.0)

```json
{
  "version": "1.1.0",
  "exportedAt": "2026-02-23T17:31:14.574567",
  "sourceDevice": "desktop",
  "session": {
    "sessionId": "097f3474-8974-4405-98c0-b70d4bf920d5",
    "messages": [...],
    "metadata": {
      "projectPath": "${PROJECTS}/my-app",
      "messageCount": 1504,
      "firstPrompt": "...",
      "created": "2026-01-15T10:00:00.000Z"
    },
    "fileHistory": {
      "09e54f171b709bcd@v2": "<tracked file content>",
      ...
    },
    "todos": [
      {"content": "Task 1", "status": "completed", "activeForm": "Working on task 1"},
      ...
    ]
  },
  "checksum": "a3f5b2c8..."
}
```

### Integrity Validation

Every bundle includes a SHA256 checksum computed over the entire session (messages + file-history + todos). If the file is corrupted or modified during transfer, the import rejects the bundle with an error.

---

## Troubleshooting

### "Session not found"
```bash
claude-sync list   # see available session IDs
```

### "Checksum mismatch"
Bundle corrupted during transfer. Re-export from the original device.

### "Session already exists"
```bash
claude-sync import session.bundle.gz --force
claude-sync sync-pull 097f3474 --force
```

### "Device not found"
```bash
claude-sync devices   # see configured devices
claude-sync config --device-id laptop --projects-path "D:/Projects" --set-current
```

### pip not recognized
```bash
python -m ensurepip --upgrade
python -m pip install -e .
```

### "Host key verification failed" (SSH)

The `.ssh` folder exists but GitHub is not in known hosts yet. Run:

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
```

### "Permission denied (publickey)" (SSH)

The SSH key is not registered on GitHub, or the `.ssh` folder did not exist when the key was generated.

```bash
# 1. Create the .ssh folder if it doesn't exist
mkdir -p ~/.ssh && chmod 700 ~/.ssh

# 2. Generate a new key
ssh-keygen -t ed25519 -C "this-pc-name" -f ~/.ssh/id_ed25519 -N ""

# 3. Add GitHub to known hosts
ssh-keyscan github.com >> ~/.ssh/known_hosts

# 4. Copy and add the public key to GitHub
cat ~/.ssh/id_ed25519.pub
# → github.com/settings/ssh/new

# 5. Test
ssh -T git@github.com
```

### sync-push fails on empty repo
Happens on the very first push to a freshly created repository. The tool detects this automatically and skips the pull step. Just run the command normally.

### Automatic hook not syncing

If automatic sync stops working after running `hooks-install`, check the hook log:

- **Windows:** `%USERPROFILE%\.claude-context-sync\logs\hook.log`
- **Linux/macOS:** `~/.claude-context-sync/logs/hook.log`

The log records every automatic sync attempt with timestamp and error details.

For more detail on a manual command, add `--verbose`:

```bash
claude-sync sync-push --verbose
claude-sync sync-pull --verbose
```

This writes step-by-step output to `~/.claude-context-sync/logs/app.log`.

### "Decryption failed — wrong passphrase or corrupted bundle"

The passphrase entered does not match the one used to encrypt the bundle. Make sure you ran `crypto-setup` with the same passphrase on both machines. If you set up a saved key (`crypto-setup`), the key files on both machines must have been derived from the same passphrase.

---

## Limitations

- No conflict resolution — use sessions alternately between devices (push from A, pull on B, work on B, push from B, pull on A)
- Automatic hooks require `claude-sync` to be on the system PATH — install via `pip install -e .`
- Requires Git installed and authenticated for Git-based sync

---

## Roadmap

### v0.3.0
- [x] Full session export: messages, file-history, todos
- [x] gzip compression (`--compress`)
- [x] Automatic progress bars
- [x] Git sync (`sync-push` / `sync-pull` / `sync-list`)
- [x] Configurable default repository (`claude-sync repo <url>`) — `--repo` optional
- [x] `sync-push` without session ID — interactive picker from current project
- [x] `sync-pull` without session ID — interactive picker from remote repository
- [x] Descriptive Git commit labels (project name + first prompt)
- [x] SHA256 integrity validation

### v0.4.0 (current)
- [x] Automatic sync hooks (`hooks-install` / `hooks-uninstall`) — SessionEnd + SessionStart
- [x] Non-interactive mode (`--auto`) for hook execution
- [x] Pull most recent bundle (`--latest`) for SessionStart hooks
- [x] Optional AES-256-GCM encryption (`--encrypt`, `crypto-setup`)
- [x] Passphrase-derived keys via PBKDF2 — no raw key file management
- [x] Structured logs: `hook.log` (always) + `app.log` (`--verbose`)

### v0.5.0 (next)
- [ ] Linux and macOS support
- [ ] `sync-push --all` to push all sessions from a project at once
- [ ] `sync-pull --all` to pull all available bundles

### v1.0.0 (future)
- [ ] Optional cloud backend
- [ ] Web dashboard
- [ ] Automatic conflict resolution

---

## Contributing

1. Fork the project
2. Create a branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push and open a Pull Request

---

## License

MIT License

## Author

Daniel de Oliveira Trindade
