"""
sharing.py — Session sharing between users.

Shares are stored in {DATA_DIR}/shares.json:
{
  "abc12345": {
    "session_prefix": "097f3474",
    "project": "claude-context-sync",
    "shared_by": "usuario-a",
    "shared_with": "usuario-b",  // or "*" for everyone
    "created_at": "2026-03-22T...",
    "message": "optional message"
  }
}
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.environ.get("SYNC_DATA_DIR", "/data"))
SHARES_FILE = DATA_DIR / "shares.json"


def _load_shares() -> dict:
    if not SHARES_FILE.exists():
        return {}
    try:
        return json.loads(SHARES_FILE.read_text())
    except Exception:
        return {}


def _save_shares(shares: dict):
    SHARES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHARES_FILE.write_text(json.dumps(shares, indent=2))


def create_share(
    session_prefix: str,
    project: str,
    shared_by: str,
    shared_with: str,
    message: str = "",
) -> str:
    """Create a share entry and return its share_id (8-char UUID prefix)."""
    shares = _load_shares()
    share_id = str(uuid.uuid4())[:8]
    # Ensure uniqueness
    while share_id in shares:
        share_id = str(uuid.uuid4())[:8]

    shares[share_id] = {
        "session_prefix": session_prefix,
        "project": project,
        "shared_by": shared_by,
        "shared_with": shared_with,
        "created_at": datetime.utcnow().isoformat(),
        "message": message,
    }
    _save_shares(shares)
    return share_id


def list_inbox(username: str) -> list:
    """Return shares where shared_with == username or '*'."""
    shares = _load_shares()
    result = []
    for share_id, data in shares.items():
        if data["shared_with"] in (username, "*"):
            result.append({"share_id": share_id, **data})
    return result


def list_outbox(username: str) -> list:
    """Return shares created by username."""
    shares = _load_shares()
    result = []
    for share_id, data in shares.items():
        if data["shared_by"] == username:
            result.append({"share_id": share_id, **data})
    return result


def get_share(share_id: str) -> Optional[dict]:
    """Return a single share dict (with share_id included), or None."""
    shares = _load_shares()
    data = shares.get(share_id)
    if data is None:
        return None
    return {"share_id": share_id, **data}


def delete_share(share_id: str, requesting_user: str, is_admin: bool):
    """Delete a share. Raises ValueError if not authorized or not found."""
    shares = _load_shares()
    if share_id not in shares:
        raise ValueError(f"Share '{share_id}' not found")
    data = shares[share_id]
    if not is_admin and data["shared_by"] != requesting_user:
        raise ValueError("Not authorized to delete this share")
    del shares[share_id]
    _save_shares(shares)


def list_all_shares() -> list:
    """Return all shares (admin only)."""
    shares = _load_shares()
    return [{"share_id": share_id, **data} for share_id, data in shares.items()]
