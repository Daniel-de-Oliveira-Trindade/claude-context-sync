# Quick Start — Use Right Now!

## How to Use (Without Installing)

Navigate to the project folder and run commands directly:

```bash
cd <path-to-claude-context-sync>
python claude-sync.py list
```

---

## Main Commands

### 1. List your sessions
```bash
python claude-sync.py list
```

### 2. Export a session
```bash
# Copy the session ID from the command above
python claude-sync.py export <session-id> --output session.bundle

# With compression (recommended):
python claude-sync.py export <session-id> --output session.bundle --compress
```

### 3. List configured devices
```bash
python claude-sync.py devices
```

### 4. Configure your device (first time only)

**Windows:**
```bash
python claude-sync.py config \
  --device-id desktop \
  --projects-path "C:/Users/<username>/Documents/projects" \
  --set-current
```

**Linux / macOS:**
```bash
python claude-sync.py config \
  --device-id desktop \
  --projects-path "/home/<username>/projects" \
  --set-current
```

---

## Full Example

```bash
# 1. Go to the project folder
cd <path-to-claude-context-sync>

# 2. Configure your device (first time only)
python claude-sync.py config --device-id desktop \
  --projects-path "C:/Users/<username>/Documents/projects" \
  --set-current

# 3. List your sessions
python claude-sync.py list

# 4. Set a default Git repository (once per device)
python claude-sync.py repo git@github.com:your-username/claude-sessions.git

# 5. Push a session interactively (run from inside the project folder)
cd C:/Users/<username>/Documents/projects/my-app
python claude-sync.py sync-push --compress

# 6. On the other PC, pull interactively
python claude-sync.py sync-pull
```

---

## Optional: Permanent Shortcut

If you want to use `claude-sync` from anywhere, install the package:

```bash
cd <path-to-claude-context-sync>
python -m pip install -e .
```

After that, you can run `claude-sync` from any directory:

```bash
claude-sync list
claude-sync sync-push --compress
claude-sync sync-pull
```

### Windows alternative (without pip)

Copy the batch script to a folder that is already in your PATH:

```cmd
copy claude-sync.bat "C:\Users\<username>\AppData\Local\Programs\Python\Python313\Scripts\claude-sync.bat"
```

Restart your terminal and use `claude-sync` from anywhere.

---

## Common Error

### "No such file or directory"

**Error:**
```
can't open file 'claude-sync.py': [Errno 2] No such file or directory
```

**Cause:** You are not in the right folder.

**Solution:** Navigate to the project folder first:
```bash
cd <path-to-claude-context-sync>
python claude-sync.py list
```

---

## Try It Now

Run this to see your 3 most recent sessions:

```bash
python claude-sync.py list --limit 3
```
