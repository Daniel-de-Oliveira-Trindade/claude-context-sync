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

import sys
import click
from pathlib import Path
from typing import Optional

from .path_transformer import PathTransformer
from .exporter import SessionExporter
from .importer import SessionImporter
from .git_sync import GitSync
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


@click.group()
@click.version_option(version="0.4.0")
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
            from .crypto import decrypt_bundle, load_key, EncryptionKeyNotFound

            try:
                key = load_key()
                passphrase = None
            except EncryptionKeyNotFound:
                passphrase = click.prompt("Bundle is encrypted. Enter passphrase", hide_input=True)
                key = None

            with open(bundle_path, "rb") as f:
                encrypted_data = f.read()
            decrypted = decrypt_bundle(encrypted_data, key=key, passphrase=passphrase)

            # Escreve temporariamente sem o .enc para importar normalmente
            decrypted_path = bundle_path[:-4]
            with open(decrypted_path, "wb") as f:
                f.write(decrypted)
            bundle_path = decrypted_path
            click.echo(f"[OK] Bundle decrypted: {Path(bundle_path).name}\n")

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
@click.argument('url')
def repo(url):
    """Set default Git repository URL for sync commands"""
    try:
        transformer = PathTransformer()
        transformer.set_default_repo(url)
        click.echo(f"[OK] Default repository set to: {url}")
        click.echo(f"     You can now run sync-push/pull/list without --repo")

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

        # 1. Gather metadata for descriptive commit label
        label = ""
        project_dir = exporter.find_project_by_session(session_id)
        if project_dir:
            index = exporter.read_sessions_index(project_dir)
            meta = exporter.find_session_metadata(index, session_id)
            if meta:
                first_prompt = meta.get('firstPrompt', '')[:50]
                project_path = meta.get('projectPath') or meta.get('fullPath', '')
                if project_path:
                    clean = project_path.replace('${PROJECTS}/', '').replace('${HOME}/', '')
                    # Use the last path component as project name (works for both
                    # template paths like "${PROJECTS}/myapp" and absolute paths)
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
            from .crypto import encrypt_bundle, load_key, EncryptionKeyNotFound

            try:
                key = load_key()
                passphrase = None
            except EncryptionKeyNotFound:
                if auto:
                    # In auto mode, no key file means no encryption — skip silently
                    key = None
                    passphrase = None
                    encrypt = False
                else:
                    passphrase = click.prompt("Encryption passphrase", hide_input=True)
                    key = None

            if encrypt:
                encrypted_output = final_output + ".enc"
                with open(final_output, "rb") as f:
                    data = f.read()
                encrypted = encrypt_bundle(data, key=key, passphrase=passphrase)
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
        dest = git_sync.push_bundle(final_output, session_id, label=label)

        logger.log_app(f"Git push OK: {Path(dest).name}")

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

    If SESSION_ID_PREFIX is omitted, lists available bundles in the repository
    and prompts you to choose one.

    Use --latest to pull the most recently pushed bundle (used by SessionStart hooks).
    Use --auto for hook mode (non-interactive, logs errors to hook.log).
    """
    import re
    UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)

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

        # --latest: pull the most recently pushed bundle
        if latest:
            bundle_path = git_sync.get_latest_bundle()
            if bundle_path is None:
                if auto:
                    # No bundles yet — not an error, just nothing to pull
                    logger.log_hook("sync-pull", "", "OK")
                    sys.exit(0)
                else:
                    click.echo("[INFO] No bundles found in repository. Nothing to pull.")
                    return
        elif session_id_prefix is None:
            # Interactive picker
            bundles = git_sync.list_bundles()

            if not bundles:
                click.echo("[ERROR] No bundles found in repository.", err=True)
                click.echo("  Push a session first with: claude-sync sync-push")
                raise click.Abort()

            labels = git_sync.get_bundle_labels()

            click.echo(f"Available bundles in repository:\n")
            for i, name in enumerate(bundles):
                label = labels.get(name, "")
                match = UUID_RE.search(name)
                prefix = match.group()[:8] if match else name[:8]
                if label:
                    click.echo(f"  [{i + 1}] {prefix}  {label}")
                else:
                    click.echo(f"  [{i + 1}] {name}")

            choice = click.prompt("\nChoose session number", type=int)
            if choice < 1 or choice > len(bundles):
                click.echo(f"[ERROR] Invalid choice: {choice}. Must be between 1 and {len(bundles)}.", err=True)
                raise click.Abort()

            chosen = bundles[choice - 1]
            match = UUID_RE.search(chosen)
            session_id_prefix = match.group()[:8] if match else chosen
            click.echo()
            bundle_path = git_sync.pull_bundle(session_id_prefix)
        else:
            bundle_path = git_sync.pull_bundle(session_id_prefix)

        if bundle_path is None:
            msg = f"No bundle found for session prefix '{session_id_prefix}'"
            if auto:
                logger.log_hook("sync-pull", session_id_prefix or "", "ERROR", Exception(msg))
                sys.exit(1)
            else:
                click.echo(f"[ERROR] {msg}", err=True)
                click.echo(f"\nAvailable bundles:")
                for name in git_sync.list_bundles():
                    click.echo(f"  - {name}")
                raise click.Abort()

        logger.log_app(f"Found bundle: {Path(bundle_path).name}")

        if not auto:
            click.echo(f"[OK] Found bundle: {Path(bundle_path).name}\n")

        # Decrypt if bundle is encrypted
        if bundle_path.endswith(".enc"):
            from .crypto import decrypt_bundle, load_key, EncryptionKeyNotFound

            try:
                key = load_key()
                passphrase = None
            except EncryptionKeyNotFound:
                if auto:
                    err = Exception("Bundle is encrypted but no key found. Run 'claude-sync crypto-setup' first.")
                    logger.log_hook("sync-pull", "", "ERROR", err)
                    sys.exit(1)
                else:
                    passphrase = click.prompt("Bundle is encrypted. Enter passphrase", hide_input=True)
                    key = None

            with open(bundle_path, "rb") as f:
                encrypted_data = f.read()
            decrypted = decrypt_bundle(encrypted_data, key=key, passphrase=passphrase)

            # Write decrypted to temp file (strip .enc extension)
            decrypted_path = bundle_path[:-4]
            with open(decrypted_path, "wb") as f:
                f.write(decrypted)
            bundle_path = decrypted_path
            logger.log_app(f"Bundle decrypted: {Path(bundle_path).name}")

        # Import session
        importer = SessionImporter()
        success = importer.import_session(bundle_path, force=force, project_path_override=resolved)

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
            logger.log_hook("sync-pull", "", "ERROR", e)
            sys.exit(1)
        else:
            click.echo(f"[ERROR] Error during sync-pull: {e}", err=True)
            raise click.Abort()


@cli.command('sync-list')
@click.option('--repo', default=None, help='Git repository URL (SSH or HTTPS, or set default with: claude-sync repo <url>)')
def sync_list(repo):
    """List bundles available in Git repository"""
    import re
    UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)

    try:
        resolved_repo = _resolve_repo(repo)
        click.echo(f"Fetching bundle list from: {resolved_repo}\n")
        git_sync = GitSync(repo_url=resolved_repo)
        bundles = git_sync.list_bundles()

        if not bundles:
            click.echo("No bundles found in repository")
            return

        labels = git_sync.get_bundle_labels()

        click.echo(f"Found {len(bundles)} bundle(s):\n")
        for name in bundles:
            match = UUID_RE.search(name)
            click.echo(f"  {name}")
            label = labels.get(name, "")
            if label:
                click.echo(f"    {label}")
            if match:
                click.echo(f"    sync-pull ID: {match.group()[:8]}")
            click.echo()

        click.echo(f"To import a bundle:")
        click.echo(f"  claude-sync sync-pull <sync-pull ID>")

    except Exception as e:
        click.echo(f"[ERROR] Error: {e}", err=True)
        raise click.Abort()


@cli.command('hooks-install')
def hooks_install():
    """Install automatic sync hooks in Claude Code (SessionEnd + SessionStart).

    After running this command, sessions will be pushed automatically when you
    close a Claude conversation and pulled when you open Claude Code.

    Run 'hooks-uninstall' to remove the hooks.
    """
    try:
        manager = HooksManager()
        results = manager.install()

        installed = [e for e, s in results.items() if s == "installed"]
        already = [e for e, s in results.items() if s == "already_installed"]

        if installed:
            click.echo(f"[OK] Hooks installed: {', '.join(installed)}")
        if already:
            click.echo(f"[--] Already installed: {', '.join(already)}")

        click.echo(f"\nHooks configured in: ~/.claude/settings.json")
        click.echo(f"Backup saved to:      ~/.claude/settings.json.bak")
        click.echo(f"\nFrom now on:")
        click.echo(f"  - When you close a Claude session → sync-push runs automatically")
        click.echo(f"  - When you open Claude Code       → sync-pull runs automatically")
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
    """Configure an encryption passphrase for automatic encrypted sync.

    The passphrase is used to derive an AES-256 key, which is saved locally.
    Run this command with the SAME passphrase on every machine you use —
    the system will then encrypt and decrypt bundles automatically.

    To use encryption manually (without saving the key), pass --encrypt to
    sync-push and enter the passphrase each time.
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

        key_path = setup_key(passphrase)
        click.echo(f"\n[OK] Encryption key saved to: {key_path}")
        click.echo(f"\nRun this command with the same passphrase on every machine.")
        click.echo(f"sync-push will now encrypt bundles automatically when using --auto.")

    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"[ERROR] Error setting up encryption: {e}", err=True)
        raise click.Abort()


if __name__ == '__main__':
    cli()
