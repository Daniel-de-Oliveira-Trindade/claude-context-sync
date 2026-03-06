"""
CLI - Command-line interface for Claude Context Sync

Available commands:
- config: Configure device path mappings
- list: List available sessions
- export: Export session to bundle file (--compress for gzip)
- import: Import session from bundle (supports .bundle and .bundle.gz)
- devices: List configured devices
- use: Set current device
- repo: Set default Git repository URL
- sync-push: Export session and push to Git repository
- sync-pull: Pull bundle from Git repository and import
- sync-list: List bundles available in Git repository
- hooks-install: Install automatic SessionEnd/SessionStart hooks in Claude Code
- hooks-uninstall: Remove automatic hooks from Claude Code
- crypto-setup: Configure encryption passphrase for automatic encrypted sync
"""

import re
import sys
import click
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .path_transformer import PathTransformer
from .exporter import SessionExporter
from .importer import SessionImporter
from .git_sync import GitSync, sanitize_project_name
from .hooks import HooksManager
from . import logger


def _resolve_repo(repo_option: Optional[str]) -> str:
    """Retorna repo_option se fornecido, senão lê o repositório padrão configurado"""
    if repo_option:
        return repo_option
    transformer = PathTransformer()
    default = transformer.get_default_repo()
    if not default:
        raise click.UsageError(
            "No default repository configured.\n"
            "Pass --repo or set a default with:\n"
            "  claude-sync repo <url>"
        )
    return default


# ---------------------------------------------------------------------------
# Display helpers for grouped bundle list (sync-list / sync-pull)
# ---------------------------------------------------------------------------

def _format_timestamp(ts: str) -> str:
    """Convert '20260307-091500' → '2026-03-07 09:15', or return ts unchanged."""
    if len(ts) == 15 and ts[8] == "-":
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}"
    return ts


def _extract_first_prompt(label: str) -> str:
    """
    Strip the commit-message prefix from a bundle label.

    Input:  "sync: session 097f3474 | claude-session-sync | Fix the bug"
    Output: "Fix the bug"

    Or if already stripped (stored directly without "sync:" prefix):
    Input:  "claude-session-sync | Fix the bug"
    Output: "Fix the bug"
    """
    parts = label.split(" | ")
    if len(parts) >= 3 and parts[0].startswith("sync:"):
        return " | ".join(parts[2:])
    if len(parts) >= 2:
        return " | ".join(parts[1:])
    return label


def _group_bundles(bundles: list, labels: dict) -> list:
    """
    Group bundle dicts by session_id_prefix, sorted newest-first within each group.

    Returns a list of group dicts sorted by (project_folder, session_prefix):
    [
        {
            "session_prefix": "097f3474",
            "project_folder": "claude-session-sync",
            "label": "sync: session 097f3474 | ...",
            "versions": [   # newest first
                {filename, timestamp, relative, path, ...},
            ]
        },
        ...
    ]
    """
    groups: dict = defaultdict(list)
    for b in bundles:
        groups[b["session_id_prefix"]].append(b)

    result = []
    for prefix, versions in groups.items():
        versions.sort(key=lambda v: v["timestamp"], reverse=True)
        latest = versions[0]
        # Prefer label keyed by relative path, fall back to filename
        label = labels.get(latest["relative"], "") or labels.get(latest["filename"], "")
        project_folder = latest["project_folder"]

        result.append({
            "session_prefix": prefix,
            "project_folder": project_folder,
            "label": label,
            "versions": versions,
        })

    result.sort(key=lambda g: (g["project_folder"], g["session_prefix"]))
    return result


def _parse_picker_choice(raw: str, groups: list):
    """
    Parse interactive picker input.

    Accepts: "2", "2a", "2 a", "2B"
    Returns: (group_index_0based, version_index_0based) or (None, None) on error.
    """
    raw = raw.strip()
    match = re.fullmatch(r'(\d+)\s*([a-z])?', raw, re.I)
    if not match:
        return None, None

    group_num = int(match.group(1))
    version_letter = match.group(2)

    if group_num < 1 or group_num > len(groups):
        return None, None

    group = groups[group_num - 1]

    if version_letter is None:
        version_idx = 0  # default: latest
    else:
        version_idx = ord(version_letter.lower()) - ord("a")
        if version_idx < 0 or version_idx >= len(group["versions"]):
            return None, None

    return group_num - 1, version_idx


def _extract_project_from_bundle(bundle_path: str) -> str:
    """
    Read bundle metadata to extract the project name (last component of projectPath).

    Used to organise backups into per-project subfolders.
    Returns "" on any error.
    """
    try:
        imp = SessionImporter()
        data = imp.read_bundle(bundle_path)
        meta = data.get("session", {}).get("metadata", {})
        pp = meta.get("projectPath", "")
        if pp:
            clean = pp.replace("${PROJECTS}/", "").replace("${HOME}/", "")
            return Path(clean).name
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="0.5.0")
def cli():
    """Claude Context Sync - Transfer Claude Code sessions between devices"""
    pass


@cli.command()
@click.option('--device-id', required=True, help='Device identifier (e.g., laptop, desktop)')
@click.option('--user', help='Windows username (defaults to current user)')
@click.option('--home', help='Home directory path (defaults to current home)')
@click.option('--projects-path', required=True, help='Path to projects directory')
@click.option('--claude-dir', help='Path to .claude directory (optional)')
@click.option('--set-current', is_flag=True, help='Set this device as current')
def config(device_id, user, home, projects_path, claude_dir, set_current):
    """Configure path mappings for a device"""
    try:
        transformer = PathTransformer()

        if user is None:
            import os
            user = os.environ.get('USERNAME', 'user')

        if home is None:
            home = str(Path.home())

        transformer.add_device(
            device_id=device_id,
            user=user,
            home=home,
            projects=projects_path,
            claude_dir=claude_dir
        )

        click.echo(f"[OK] Device '{device_id}' configured successfully")
        click.echo(f"   User: {user}")
        click.echo(f"   Home: {home}")
        click.echo(f"   Projects: {projects_path}")
        click.echo(f"   Claude Dir: {claude_dir or Path(home) / '.claude'}")

        if set_current:
            transformer.set_current_device(device_id)
            click.echo(f"[OK] '{device_id}' set as current device")

        valid, errors = transformer.validate_mappings()
        if not valid:
            click.echo("\n[WARNING] Configuration warnings:")
            for error in errors:
                click.echo(f"   - {error}")

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--project', help='Filter by project path')
@click.option('--limit', default=20, help='Maximum number of sessions to show')
def list(project, limit):
    """List available sessions"""
    try:
        exporter = SessionExporter()
        sessions = exporter.list_sessions(project_path=project)

        if not sessions:
            click.echo("No sessions found")
            return

        sessions = sessions[:limit]

        click.echo(f"\nFound {len(sessions)} session(s):\n")

        for session in sessions:
            session_id = session.get('sessionId', 'unknown')
            first_prompt = session.get('firstPrompt', '')
            message_count = session.get('messageCount', 0)
            created = session.get('created', '')
            modified = session.get('modified', '')
            project_dir = session.get('_projectDir', '')

            if len(first_prompt) > 60:
                first_prompt = first_prompt[:57] + "..."

            click.echo(f"Session ID: {session_id}")
            click.echo(f"  First prompt: {first_prompt}")
            click.echo(f"  Messages: {message_count}")
            click.echo(f"  Created: {created}")
            click.echo(f"  Modified: {modified}")
            if project_dir:
                click.echo(f"  Project: {project_dir}")
            click.echo()

        if len(sessions) >= limit:
            click.echo(f"(Showing first {limit} sessions. Use --limit to see more)")

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('session_id')
@click.option('--output', default='session.bundle', help='Output bundle file path')
@click.option('--compress', is_flag=True, default=False, help='Compress bundle with gzip (.gz)')
def export(session_id, output, compress):
    """Export a session to bundle file"""
    try:
        click.echo(f"Exporting session: {session_id}")
        click.echo(f"Output file: {output}")
        if compress:
            click.echo("Compression: enabled (gzip)\n")
        else:
            click.echo()

        exporter = SessionExporter()
        success = exporter.export_session(session_id, output, compress=compress)

        if success:
            # Calcular nome real do arquivo (pode ter .gz adicionado)
            final_output = output
            if compress and not output.endswith('.gz'):
                final_output = output + '.gz'

            click.echo(f"\n[SUCCESS] Export completed successfully!")
            click.echo(f"\nNext steps:")
            click.echo(f"1. Transfer '{final_output}' to your other device")
            click.echo(f"2. Run: claude-sync import {final_output}")

    except FileNotFoundError as e:
        click.echo(f"[ERROR] {e}", err=True)
        click.echo(f"\nTip: Use 'claude-sync list' to see available sessions")
        raise click.Abort()

    except Exception as e:
        click.echo(f"[ERROR] Error during export: {e}", err=True)
        raise click.Abort()


@cli.command(name='import')
@click.argument('bundle_path')
@click.option('--force', is_flag=True, help='Overwrite existing session')
@click.option('--project-path', default=None,
              help='Local project path on this device (default: current directory)')
def import_cmd(bundle_path, force, project_path):
    """Import a session from bundle file (.bundle, .bundle.gz, or .bundle.gz.enc)"""
    try:
        resolved = project_path or str(Path.cwd())
        click.echo(f"Importing session from: {bundle_path}")
        click.echo(f"Using project path: {resolved}")
        if not project_path:
            click.echo(f"  (use --project-path to change)\n")
        else:
            click.echo()

        # Decrypt if bundle is encrypted
        if bundle_path.endswith(".enc"):
            from .crypto import decrypt_bundle, load_passphrase, PassphraseNotFound

            try:
                passphrase = load_passphrase()
            except PassphraseNotFound:
                passphrase = click.prompt("Bundle is encrypted. Enter passphrase", hide_input=True)

            with open(bundle_path, "rb") as f:
                encrypted_data = f.read()
            decrypted = decrypt_bundle(encrypted_data, passphrase=passphrase)

            # Write decrypted bytes to a temp file (strip .enc) and import normally
            decrypted_path = bundle_path[:-4]
            with open(decrypted_path, "wb") as f:
                f.write(decrypted)
            bundle_path = decrypted_path
            click.echo(f"[OK] Bundle decrypted: {Path(bundle_path).name}\n")

        # Save local backup if a default repo is configured
        try:
            transformer = PathTransformer()
            default_repo = transformer.get_default_repo()
            if default_repo:
                gs = GitSync(repo_url=default_repo)
                backup_project = _extract_project_from_bundle(bundle_path)
                bp = gs.save_local_backup(
                    bundle_path, Path(bundle_path).name[:8],
                    project_name=backup_project
                )
                if bp:
                    click.echo(f"[OK] Local backup saved: {Path(bp).name}\n")
        except Exception:
            pass  # Backup failure must never block the import

        importer = SessionImporter()
        success = importer.import_session(bundle_path, force=force, project_path_override=resolved)

        if success:
            click.echo(f"\n[SUCCESS] Import completed successfully!")
            click.echo(f"\nYou can now resume this session in Claude Code")

    except FileNotFoundError as e:
        click.echo(f"[ERROR] {e}", err=True)
        raise click.Abort()

    except FileExistsError as e:
        click.echo(f"[ERROR] {e}", err=True)
        click.echo(f"\nTip: Use --force to overwrite the existing session")
        raise click.Abort()

    except ValueError as e:
        click.echo(f"[ERROR] {e}", err=True)
        raise click.Abort()

    except Exception as e:
        import json as _json
        if isinstance(e, _json.JSONDecodeError):
            click.echo("[ERROR] Failed to read bundle — the file may be corrupted or decryption used the wrong key/passphrase.", err=True)
        else:
            click.echo(f"[ERROR] Error during import: {e}", err=True)
        raise click.Abort()


@cli.command()
def devices():
    """List configured devices"""
    try:
        transformer = PathTransformer()
        devs = transformer.list_devices()
        current = transformer.current_device

        if not devs:
            click.echo("No devices configured")
            click.echo("\nUse 'claude-sync config' to add a device")
            return

        click.echo(f"\nConfigured devices:\n")

        for device_id, mapping in devs.items():
            marker = "* CURRENT" if device_id == current else ""
            click.echo(f"{device_id} {marker}")
            click.echo(f"  User: {mapping.get('USER')}")
            click.echo(f"  Home: {mapping.get('HOME')}")
            click.echo(f"  Projects: {mapping.get('PROJECTS')}")
            click.echo(f"  Claude Dir: {mapping.get('CLAUDE_DIR')}")
            click.echo()

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('device_id')
def use(device_id):
    """Set current device"""
    try:
        transformer = PathTransformer()
        transformer.set_current_device(device_id)

        click.echo(f"[OK] Current device set to: {device_id}")

    except ValueError as e:
        click.echo(f"[ERROR] {e}", err=True)
        click.echo(f"\nUse 'claude-sync devices' to see available devices")
        raise click.Abort()

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('url', required=False, default=None)
def repo(url):
    """Set or show default Git repository URL for sync commands.

    Without arguments, shows the currently configured repository.
    With a URL argument, sets it as the new default.
    """
    try:
        transformer = PathTransformer()
        if url:
            transformer.set_default_repo(url)
            click.echo(f"[OK] Default repository set to: {url}")
            click.echo(f"     You can now run sync-push/pull/list without --repo")
        else:
            current = transformer.get_default_repo()
            if current:
                click.echo(f"[OK] Default repository: {current}")
            else:
                click.echo("[INFO] No default repository configured.")
                click.echo("       Run: claude-sync repo <url>")

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command('sync-push')
@click.argument('session_id', required=False, default=None)
@click.option('--session', 'session_opt', default=None, help='Session UUID (alternative to positional argument)')
@click.option('--repo', default=None, help='Git repository URL (SSH or HTTPS, or set default with: claude-sync repo <url>)')
@click.option('--output', default=None, help='Bundle filename (default: <session-id>.bundle)')
@click.option('--compress', is_flag=True, default=False, help='Compress bundle with gzip')
@click.option('--encrypt', is_flag=True, default=False, help='Encrypt bundle with AES-256-GCM (requires crypto-setup or prompts for passphrase)')
@click.option('--auto', is_flag=True, default=False, help='Non-interactive mode for hooks: no prompts, errors go to log file')
@click.option('--verbose', is_flag=True, default=False, help='Write detailed output to ~/.claude-context-sync/logs/app.log')
def sync_push(session_id, session_opt, repo, output, compress, encrypt, auto, verbose):
    """Export session and push to Git repository.

    If SESSION_ID is omitted, lists sessions in the current project directory
    and prompts you to choose one.

    Use --auto for hook mode (non-interactive, logs errors to hook.log).
    Use --session UUID to specify a session directly (used by SessionEnd hooks).
    """
    if verbose:
        logger.set_verbose(True)

    # --session option takes precedence over positional argument
    if session_opt:
        session_id = session_opt

    # On Windows, $CLAUDE_SESSION_ID is not expanded by the shell — read from env directly
    import os as _os
    if session_id and session_id.startswith("$"):
        env_var = session_id.lstrip("$")
        session_id = _os.environ.get(env_var) or _os.environ.get(env_var.upper()) or None

    def _abort(message: str, error: Exception = None):
        """Handle errors differently in auto vs interactive mode."""
        if auto:
            logger.log_hook("sync-push", session_id or "", "ERROR", error or Exception(message))
            sys.exit(1)
        else:
            click.echo(f"[ERROR] {message}", err=True)
            raise click.Abort()

    try:
        resolved_repo = _resolve_repo(repo)
        exporter = SessionExporter()

        # No session_id in auto mode: cannot use interactive picker
        if session_id is None and auto:
            _abort("--auto requires --session SESSION_ID")
            return

        # No session_id in interactive mode: show picker
        if session_id is None:
            sessions = exporter.list_sessions(project_path=str(Path.cwd()))

            if not sessions:
                click.echo("[ERROR] No sessions found for the current directory.", err=True)
                click.echo("  Run from inside a project folder, or pass a session ID explicitly.")
                click.echo("  Example: claude-sync sync-push 097f3474-...")
                raise click.Abort()

            click.echo(f"Sessions in current project ({Path.cwd().name}):\n")
            for i, s in enumerate(sessions):
                prompt = s.get('firstPrompt', '')[:60]
                modified = s.get('modified', '')[:10]
                click.echo(f"  [{i + 1}] {s['sessionId'][:8]}  {modified}  {prompt}")

            choice = click.prompt("\nChoose session number", type=int)
            if choice < 1 or choice > len(sessions):
                click.echo(f"[ERROR] Invalid choice: {choice}. Must be between 1 and {len(sessions)}.", err=True)
                raise click.Abort()

            session_id = sessions[choice - 1]['sessionId']
            click.echo()

        # Default output name includes session-id + timestamp to avoid collisions
        if output is None:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            output = f"{session_id}_{ts}.bundle"

        # 1. Gather metadata for descriptive commit label and project folder
        label = ""
        project_name = ""
        project_dir = exporter.find_project_by_session(session_id)
        if project_dir:
            index = exporter.read_sessions_index(project_dir)
            meta = exporter.find_session_metadata(index, session_id)
            if meta:
                first_prompt = meta.get('firstPrompt', '')[:50]
                project_path = meta.get('projectPath') or meta.get('fullPath', '')
                if project_path:
                    clean = project_path.replace('${PROJECTS}/', '').replace('${HOME}/', '')
                    project_name = Path(clean).name or project_dir.name.split('--')[-1]
                else:
                    project_name = project_dir.name.split('--')[-1]
                label = f"{project_name} | {first_prompt}"

        # 2. Export session locally
        if not auto:
            click.echo(f"Exporting session: {session_id}\n")
        logger.log_app(f"Exporting session {session_id[:8]}...")
        exporter.export_session(session_id, output, compress=compress)

        final_output = output
        if compress and not output.endswith('.gz'):
            final_output = output + '.gz'

        logger.log_app(f"Bundle written: {final_output}")

        # 3. Optionally encrypt the bundle
        if encrypt:
            from .crypto import encrypt_bundle, load_passphrase, PassphraseNotFound

            try:
                passphrase = load_passphrase()
            except PassphraseNotFound:
                if auto:
                    # In auto mode, no saved passphrase means skip encryption silently
                    encrypt = False
                    passphrase = None
                else:
                    passphrase = click.prompt("Encryption passphrase", hide_input=True)

            if encrypt:
                encrypted_output = final_output + ".enc"
                with open(final_output, "rb") as f:
                    data = f.read()
                encrypted = encrypt_bundle(data, passphrase=passphrase)
                with open(encrypted_output, "wb") as f:
                    f.write(encrypted)
                import os
                os.remove(final_output)
                final_output = encrypted_output
                logger.log_app(f"Bundle encrypted: {final_output}")

        # 4. Push to Git repo
        if not auto:
            click.echo(f"\nPushing to Git repository: {resolved_repo}")
        logger.log_app(f"Pushing to {resolved_repo}...")
        git_sync = GitSync(repo_url=resolved_repo)
        dest = git_sync.push_bundle(final_output, session_id, label=label, project_name=project_name)

        logger.log_app(f"Git push OK: {Path(dest).name}")

        # Save local backup (silent — does not affect the main flow on failure)
        try:
            backup_path = git_sync.save_local_backup(final_output, session_id[:8], project_name=project_name)
            if backup_path:
                logger.log_app(f"Local backup saved: {Path(backup_path).name}")
        except Exception:
            pass

        if auto:
            logger.log_hook("sync-push", session_id, "OK")
        else:
            click.echo(f"[OK] Bundle pushed to repository: {Path(dest).name}")
            click.echo(f"\n[SUCCESS] Session synced to Git successfully!")
            click.echo(f"\nOn another device, run:")
            click.echo(f"  claude-sync sync-pull {session_id[:8]}")

    except FileNotFoundError as e:
        if auto:
            logger.log_hook("sync-push", session_id or "", "ERROR", e)
            sys.exit(1)
        else:
            click.echo(f"[ERROR] {e}", err=True)
            click.echo(f"\nTip: Use 'claude-sync list' to see available sessions")
            raise click.Abort()

    except Exception as e:
        if auto:
            logger.log_hook("sync-push", session_id or "", "ERROR", e)
            sys.exit(1)
        else:
            click.echo(f"[ERROR] Error during sync-push: {e}", err=True)
            raise click.Abort()


@cli.command('sync-pull')
@click.argument('session_id_prefix', required=False, default=None)
@click.option('--repo', default=None, help='Git repository URL (SSH or HTTPS, or set default with: claude-sync repo <url>)')
@click.option('--force', is_flag=True, help='Overwrite existing session')
@click.option('--project-path', default=None,
              help='Local project path on this device (default: current directory)')
@click.option('--latest', is_flag=True, default=False, help='Pull the most recently pushed bundle (used by SessionStart hooks)')
@click.option('--auto', is_flag=True, default=False, help='Non-interactive mode for hooks: no prompts, errors go to log file')
@click.option('--verbose', is_flag=True, default=False, help='Write detailed output to ~/.claude-context-sync/logs/app.log')
def sync_pull(session_id_prefix, repo, force, project_path, latest, auto, verbose):
    """Pull bundle from Git repository and import session.

    If SESSION_ID_PREFIX is omitted, shows an interactive grouped picker.
    Choose a session with [N] (latest version) or [Na] / [Nb] (specific version).

    Use --latest to pull the most recently pushed bundle (used by SessionStart hooks).
    Use --auto for hook mode (non-interactive, logs errors to hook.log).
    """
    if verbose:
        logger.set_verbose(True)

    try:
        resolved_repo = _resolve_repo(repo)
        resolved = project_path or str(Path.cwd())

        if not auto:
            click.echo(f"Pulling from Git repository: {resolved_repo}")
            click.echo(f"Using project path: {resolved}")
            if not project_path:
                click.echo(f"  (use --project-path to change)\n")
            else:
                click.echo()

        logger.log_app(f"Pulling from {resolved_repo}...")
        git_sync = GitSync(repo_url=resolved_repo)

        # --latest: pull the most recently pushed bundle (used by SessionStart hook)
        if latest:
            bundle_path = git_sync.get_latest_bundle()
            if bundle_path is None:
                if auto:
                    logger.log_hook("sync-pull", "", "OK")
                    sys.exit(0)
                else:
                    click.echo("[INFO] No bundles found in repository. Nothing to pull.")
                    return
        elif session_id_prefix is None:
            # Interactive grouped picker
            bundles = git_sync.list_bundles()

            if not bundles:
                click.echo("[ERROR] No bundles found in repository.", err=True)
                click.echo("  Push a session first with: claude-sync sync-push")
                raise click.Abort()

            labels = git_sync.get_bundle_labels()
            groups = _group_bundles(bundles, labels)

            click.echo(f"Available sessions in repository:\n")
            for i, group in enumerate(groups, 1):
                project_display = group["project_folder"] or "(sem-projeto)"
                first_prompt = _extract_first_prompt(group["label"]) if group["label"] else ""
                header = f"[{i}] {group['session_prefix']} — {project_display}"
                if first_prompt:
                    header += f"  |  {first_prompt}"
                click.echo(header)

                for j, v in enumerate(group["versions"]):
                    sub = chr(ord("a") + j)
                    ts_display = _format_timestamp(v["timestamp"]) if v["timestamp"] else "(no date)"
                    latest_tag = "  <- latest" if j == 0 else ""
                    click.echo(f"    [{sub}] {ts_display}  {v['filename']}{latest_tag}")
                click.echo()

            raw_choice = click.prompt(
                "Choose session [number] or [number+letter] for specific version (e.g. 1, 2a, 2b)"
            )
            group_idx, version_idx = _parse_picker_choice(raw_choice, groups)
            if group_idx is None:
                click.echo(f"[ERROR] Invalid choice: {raw_choice!r}", err=True)
                raise click.Abort()

            chosen_group = groups[group_idx]
            chosen_version = chosen_group["versions"][version_idx]
            session_id_prefix = chosen_group["session_prefix"]
            bundle_path = chosen_version["path"]
            click.echo()
        else:
            bundle_path = git_sync.pull_bundle(session_id_prefix)

        if bundle_path is None:
            msg = f"No bundle found for session prefix '{session_id_prefix}'"
            if auto:
                logger.log_hook("sync-pull", session_id_prefix or "", "ERROR", Exception(msg))
                sys.exit(1)
            else:
                click.echo(f"[ERROR] {msg}", err=True)
                click.echo(f"\nRun 'claude-sync sync-list' to see available bundles.")
                raise click.Abort()

        logger.log_app(f"Found bundle: {Path(bundle_path).name}")

        if not auto:
            click.echo(f"[OK] Found bundle: {Path(bundle_path).name}\n")

        # Decrypt if bundle is encrypted
        if bundle_path.endswith(".enc"):
            from .crypto import decrypt_bundle, load_passphrase, PassphraseNotFound

            try:
                passphrase = load_passphrase()
            except PassphraseNotFound:
                if auto:
                    err = Exception("Bundle is encrypted but no passphrase saved. Run 'claude-sync crypto-setup' first.")
                    logger.log_hook("sync-pull", "", "ERROR", err)
                    sys.exit(1)
                else:
                    passphrase = click.prompt("Bundle is encrypted. Enter passphrase", hide_input=True)

            with open(bundle_path, "rb") as f:
                encrypted_data = f.read()
            decrypted = decrypt_bundle(encrypted_data, passphrase=passphrase)

            decrypted_path = bundle_path[:-4]
            with open(decrypted_path, "wb") as f:
                f.write(decrypted)
            bundle_path = decrypted_path
            logger.log_app(f"Bundle decrypted: {Path(bundle_path).name}")

        # Save local backup before importing
        try:
            backup_project = _extract_project_from_bundle(bundle_path)
            backup_path = git_sync.save_local_backup(
                bundle_path, session_id_prefix or Path(bundle_path).name[:8],
                project_name=backup_project
            )
            if backup_path:
                logger.log_app(f"Local backup saved: {Path(backup_path).name}")
        except Exception:
            pass  # Backup failure must never block the import

        # Import session — in auto mode always force-overwrite (hook must stay up to date)
        importer = SessionImporter()
        success = importer.import_session(bundle_path, force=force or auto, project_path_override=resolved)

        if success:
            if auto:
                logger.log_hook("sync-pull", "", "OK")
            else:
                click.echo(f"\n[SUCCESS] Session synced from Git successfully!")
                click.echo(f"\nYou can now resume this session in Claude Code")

    except FileExistsError as e:
        if auto:
            logger.log_hook("sync-pull", "", "ERROR", e)
            sys.exit(1)
        else:
            click.echo(f"[ERROR] {e}", err=True)
            click.echo(f"\nTip: Use --force to overwrite the existing session")
            raise click.Abort()

    except ValueError as e:
        if auto:
            logger.log_hook("sync-pull", "", "ERROR", e)
            sys.exit(1)
        else:
            click.echo(f"[ERROR] {e}", err=True)
            raise click.Abort()

    except Exception as e:
        if auto:
            # In auto (SessionStart hook) mode, network/git errors are non-critical:
            # the user may be offline or the repo may be temporarily unavailable.
            # Always log to hook.log, but exit 0 for transient errors so the IDE
            # does not show a scary error notification on every startup.
            import subprocess as _sp
            is_transient = isinstance(e, _sp.CalledProcessError) or any(
                kw in str(e).lower() for kw in ("git", "ssh", "network", "connection", "timeout", "remote")
            )
            logger.log_hook("sync-pull", "", "ERROR", e)
            sys.exit(0 if is_transient else 1)
        else:
            click.echo(f"[ERROR] Error during sync-pull: {e}", err=True)
            raise click.Abort()


@cli.command('sync-list')
@click.option('--repo', default=None, help='Git repository URL (SSH or HTTPS, or set default with: claude-sync repo <url>)')
def sync_list(repo):
    """List bundles available in Git repository, grouped by session."""
    try:
        resolved_repo = _resolve_repo(repo)
        click.echo(f"Fetching bundle list from: {resolved_repo}\n")
        git_sync = GitSync(repo_url=resolved_repo)
        bundles = git_sync.list_bundles()

        if not bundles:
            click.echo("No bundles found in repository")
            return

        labels = git_sync.get_bundle_labels()
        groups = _group_bundles(bundles, labels)

        click.echo(f"Found {len(bundles)} bundle(s) in {len(groups)} session(s):\n")

        for i, group in enumerate(groups, 1):
            project_display = group["project_folder"] or "(sem-projeto)"
            first_prompt = _extract_first_prompt(group["label"]) if group["label"] else ""
            header = f"[{i}] {group['session_prefix']} — {project_display}"
            if first_prompt:
                header += f"  |  {first_prompt}"
            click.echo(header)

            for j, v in enumerate(group["versions"]):
                sub = chr(ord("a") + j)
                ts_display = _format_timestamp(v["timestamp"]) if v["timestamp"] else "(no date)"
                latest_tag = "  <- latest" if j == 0 else ""
                click.echo(f"    [{sub}] {ts_display}  {v['filename']}{latest_tag}")
            click.echo()

        click.echo(f"To import a session:")
        click.echo(f"  claude-sync sync-pull <session-prefix>")
        click.echo(f"  claude-sync sync-pull  (interactive picker)")

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command('hooks-install')
@click.option('--force', is_flag=True, default=False,
              help='Overwrite existing hooks with the current version')
def hooks_install(force):
    """Install automatic sync hooks in Claude Code (SessionEnd + SessionStart).

    After running this command, sessions will be pushed automatically when you
    close a Claude conversation and pulled when you open Claude Code.

    If hooks are already installed, shows their current commands without modifying
    anything. Use --force to update them to the current version.

    Run 'hooks-uninstall' to remove the hooks.
    """
    try:
        manager = HooksManager()
        results = manager.install(force=force)

        installed = [e for e, s in results.items() if s == "installed"]
        updated = [e for e, s in results.items() if s == "updated"]
        already = [e for e, s in results.items() if s == "already_installed"]

        # Case 1: all already installed, no --force
        if already and not installed and not updated:
            cmds = manager.get_installed_commands()
            click.echo("[--] Hooks already installed:")
            for event in already:
                cmd = cmds.get(event, "(command not found)")
                click.echo(f"     {event:<14}: {cmd}")
            click.echo()
            click.echo("To update hooks to the current version, run:")
            click.echo("  claude-sync hooks-install --force")
            return

        # Case 2: --force update
        if updated:
            click.echo(f"[OK] Hooks updated (force reinstall):")
            for event in updated:
                click.echo(f"     {event}: updated")
        # Case 3: fresh install
        if installed:
            click.echo(f"[OK] Hooks installed: {', '.join(installed)}")

        click.echo(f"\nHooks configured in: ~/.claude/settings.json")
        click.echo(f"Backup saved to:      ~/.claude/settings.json.bak")
        click.echo(f"\nFrom now on:")
        click.echo(f"  - When you close a Claude session: sync-push runs automatically")
        click.echo(f"  - When you open Claude Code:       sync-pull runs automatically")
        click.echo(f"\nTo remove hooks, run: claude-sync hooks-uninstall")

    except Exception as e:
        click.echo(f"[ERROR] Error installing hooks: {e}", err=True)
        raise click.Abort()


@cli.command('hooks-uninstall')
def hooks_uninstall():
    """Remove automatic sync hooks from Claude Code settings."""
    try:
        manager = HooksManager()
        results = manager.uninstall()

        removed = [e for e, s in results.items() if s == "removed"]
        not_found = [e for e, s in results.items() if s == "not_found"]

        if removed:
            click.echo(f"[OK] Hooks removed: {', '.join(removed)}")
        if not_found:
            click.echo(f"[--] Not found (already removed): {', '.join(not_found)}")

        click.echo(f"\nBackup saved to: ~/.claude/settings.json.bak")

    except Exception as e:
        click.echo(f"[ERROR] Error removing hooks: {e}", err=True)
        raise click.Abort()


@cli.command('crypto-setup')
def crypto_setup():
    """Save an encryption passphrase for automatic encrypted sync.

    The passphrase is saved locally and used to encrypt/decrypt bundles.
    Run this command with the SAME passphrase on every machine you use —
    bundles encrypted on one machine will then be decryptable on any other.

    To use encryption without saving the passphrase, pass --encrypt to
    sync-push and enter the passphrase each time when prompted.
    """
    try:
        from .crypto import setup_key
    except ImportError:
        click.echo("Error: the 'cryptography' package is required for encryption.", err=True)
        click.echo("Install it with:\n  pip install cryptography", err=True)
        raise click.Abort()

    try:
        passphrase = click.prompt("Enter passphrase", hide_input=True)
        confirm = click.prompt("Confirm passphrase", hide_input=True)

        if passphrase != confirm:
            click.echo("[ERROR] Passphrases do not match.", err=True)
            raise click.Abort()

        if len(passphrase) < 8:
            click.echo("[ERROR] Passphrase must be at least 8 characters.", err=True)
            raise click.Abort()

        saved_path = setup_key(passphrase)
        click.echo(f"\n[OK] Passphrase saved to: {saved_path}")
        click.echo(f"\nRun this command with the same passphrase on every machine.")
        click.echo(f"sync-push will now encrypt bundles automatically when using --encrypt or --auto.")

    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"[ERROR] Error setting up encryption: {e}", err=True)
        raise click.Abort()


if __name__ == '__main__':
    cli()
