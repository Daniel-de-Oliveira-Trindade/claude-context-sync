# Installing Claude Context Sync

## Method 1: Run directly (Simplest)

Navigate to the project folder whenever you want to use it:

```bash
cd <path-to-claude-context-sync>
python claude-sync.py <command>
```

Example:
```bash
cd <path-to-claude-context-sync>
python claude-sync.py list
python claude-sync.py export <session-id>
```

---

## Method 2: Install with pip (Recommended)

This makes `claude-sync` available from any directory.

```bash
cd <path-to-claude-context-sync>
python -m pip install -e .
```

After installation, use from anywhere:
```bash
claude-sync --help
claude-sync list
claude-sync sync-push --compress
```

If `pip` is not found:
```bash
python -m ensurepip --upgrade
python -m pip install -e .
```

---

## Method 3: Permanent alias (Windows, without pip)

### Using a batch script

1. **Copy the batch file to a folder already in your PATH:**

```cmd
copy claude-sync.bat "C:\Users\<username>\AppData\Local\Programs\Python\Python313\Scripts\claude-sync.bat"
```

2. **Or add the project folder to your Windows PATH:**

   a. Press `Win + X` and select "System"

   b. Click "Advanced system settings"

   c. Click "Environment Variables"

   d. Under "User variables", find `Path` and click "Edit"

   e. Click "New" and add the full path to the `claude-context-sync` folder

   f. Click "OK" on all windows

3. **Restart your terminal** and test:
   ```cmd
   claude-sync --help
   claude-sync list
   ```

### Using a shell alias (Linux / macOS)

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
alias claude-sync="python /path/to/claude-context-sync/claude-sync.py"
```

Then reload:
```bash
source ~/.bashrc
```

---

## Verify the Installation

```bash
# Check version
claude-sync --version

# List sessions
claude-sync list

# List configured devices
claude-sync devices

# Show help
claude-sync --help
```

---

## Troubleshooting

### "command not found" or "not recognized"

**Problem:** The terminal can't find the `claude-sync` command.

**Solution:**
1. Check that the folder was added to PATH correctly
2. Restart the terminal (CMD / PowerShell / bash)
3. Use Method 1 (direct path) as a temporary workaround

### "python: No such file or directory"

**Problem:** Python is not in PATH.

**Solution:**
```bash
# Windows — use the full Python path
"C:\Users\<username>\AppData\Local\Programs\Python\Python313\python.exe" claude-sync.py --help

# Linux / macOS
python3 claude-sync.py --help
```

### "ModuleNotFoundError: No module named 'click'"

**Problem:** Dependencies are not installed.

**Solution:**
```bash
python -m ensurepip --default-pip
pip install click tqdm
# or install the whole project:
pip install -e .
```

---

## Quick Start After Installation

```bash
# 1. Configure the current device (once per device)
claude-sync config --device-id desktop \
  --projects-path "C:/Users/<username>/Documents/projects" \
  --set-current

# 2. Set the default Git repository (once per device)
claude-sync repo git@github.com:your-username/claude-sessions.git

# 3. List your sessions
claude-sync list

# 4. Push a session (run from inside the project folder)
cd C:/Users/<username>/Documents/projects/my-app
claude-sync sync-push --compress

# 5. On another PC, pull the session
claude-sync sync-pull
```

See [README.md](README.md) for the full documentation.
