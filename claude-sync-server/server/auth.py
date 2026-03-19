"""
auth.py — JWT token management + user store.

Users are stored in {DATA_DIR}/users.json:
{
  "usuario-a": {
    "token_hash": "...",   # sha256 of the raw token
    "is_admin": false,
    "created_at": "2026-03-19T..."
  }
}

Tokens are opaque strings (UUID4-based), never stored in plain text.
"""

import json
import hashlib
import secrets
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

DATA_DIR = Path(os.environ.get("SYNC_DATA_DIR", "/data"))
USERS_FILE = DATA_DIR / "users.json"

bearer_scheme = HTTPBearer()


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text())


def _save_users(users: dict):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token(username: str, is_admin: bool = False) -> str:
    """Create a new user and return their raw token. Call once per user."""
    users = _load_users()
    if username in users:
        raise ValueError(f"User '{username}' already exists")
    token = secrets.token_urlsafe(32)
    users[username] = {
        "token_hash": _hash_token(token),
        "is_admin": is_admin,
        "created_at": datetime.utcnow().isoformat(),
    }
    _save_users(users)
    return token


def delete_user(username: str):
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found")
    del users[username]
    _save_users(users)


def list_users() -> list[dict]:
    users = _load_users()
    return [
        {"username": u, "is_admin": d["is_admin"], "created_at": d["created_at"]}
        for u, d in users.items()
    ]


def _resolve_user(token: str) -> Optional[tuple[str, bool]]:
    """Return (username, is_admin) for a valid token, or None."""
    h = _hash_token(token)
    for username, data in _load_users().items():
        if data["token_hash"] == h:
            return username, data["is_admin"]
    return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)):
    result = _resolve_user(credentials.credentials)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"username": result[0], "is_admin": result[1]}


def require_admin(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)):
    result = _resolve_user(credentials.credentials)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not result[1]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"username": result[0], "is_admin": True}
