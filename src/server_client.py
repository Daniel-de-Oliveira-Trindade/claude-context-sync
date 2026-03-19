"""
server_client.py — HTTP client for the Claude Sync Central Server.

Used by sync-push, sync-pull, sync-list when a server URL is configured.
Falls back to git when server is unavailable.
"""

import os
import json
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".claude-context-sync"
SERVER_CONFIG_FILE = CONFIG_DIR / "server.json"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_server_config() -> dict:
    if not SERVER_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(SERVER_CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_server_config(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SERVER_CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_server_url() -> Optional[str]:
    return get_server_config().get("server_url")


def get_token() -> Optional[str]:
    return get_server_config().get("token")


def set_server_url(url: str):
    cfg = get_server_config()
    cfg["server_url"] = url.rstrip("/")
    save_server_config(cfg)


def set_token(token: str):
    cfg = get_server_config()
    cfg["token"] = token
    save_server_config(cfg)


# ---------------------------------------------------------------------------
# HTTP operations
# ---------------------------------------------------------------------------

def _headers() -> dict:
    token = get_token()
    if not token:
        raise RuntimeError("No server token configured. Run: claude-sync token --save TOKEN")
    return {"Authorization": f"Bearer {token}"}


def push_bundle(bundle_path: Path, project: str) -> dict:
    """Upload a bundle file to the server. Returns server response dict."""
    import urllib.request
    import urllib.parse

    url = get_server_url()
    if not url:
        raise RuntimeError("No server URL configured")

    # Use requests if available, otherwise urllib multipart
    try:
        import requests
        with open(bundle_path, "rb") as f:
            resp = requests.post(
                f"{url}/api/sessions/push",
                headers=_headers(),
                data={"project": project, "filename": bundle_path.name},
                files={"file": (bundle_path.name, f, "application/octet-stream")},
                timeout=120,
            )
        resp.raise_for_status()
        return resp.json()
    except ImportError:
        raise RuntimeError("requests library required for server mode: pip install requests")


def list_sessions(project: Optional[str] = None) -> list[dict]:
    """List bundles from server."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests library required for server mode: pip install requests")

    url = get_server_url()
    params = {}
    if project:
        params["project"] = project
    resp = requests.get(f"{url}/api/sessions", headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("bundles", [])


def pull_bundle(session_prefix: str, dest_dir: Path, filename: Optional[str] = None) -> Path:
    """Download a bundle from server. Returns local path of downloaded file."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests library required for server mode: pip install requests")

    url = get_server_url()
    params = {}
    if filename:
        params["filename"] = filename
    resp = requests.get(
        f"{url}/api/sessions/{session_prefix}",
        headers=_headers(),
        params=params,
        timeout=120,
        stream=True,
    )
    resp.raise_for_status()

    # Get filename from Content-Disposition or params
    out_filename = filename
    if not out_filename:
        cd = resp.headers.get("content-disposition", "")
        if "filename=" in cd:
            out_filename = cd.split("filename=")[-1].strip().strip('"')
        else:
            out_filename = f"{session_prefix}_download.bundle.gz"

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / out_filename
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return out_path


def create_admin_user(username: str, is_admin: bool = False) -> dict:
    """Admin: create a new user and get their token."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests library required")

    url = get_server_url()
    resp = requests.post(
        f"{url}/api/admin/users",
        headers=_headers(),
        data={"username": username, "is_admin": str(is_admin).lower()},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def health_check() -> bool:
    """Return True if server is reachable."""
    try:
        import requests
        url = get_server_url()
        if not url:
            return False
        resp = requests.get(f"{url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
