"""
main.py — Claude Sync Central Server (FastAPI).

Endpoints:
  POST   /api/sessions/push                → upload bundle
  GET    /api/sessions                     → list my sessions
  GET    /api/sessions/{prefix}            → download latest bundle for session
  GET    /api/sessions/{prefix}/versions   → list all versions of a session
  DELETE /api/sessions/{prefix}            → delete all versions of a session

  POST   /api/admin/users                  → create user (admin)
  DELETE /api/admin/users/{username}       → delete user (admin)
  GET    /api/admin/users                  → list users (admin)
  GET    /api/admin/sessions               → all sessions, all users (admin)
  GET    /api/admin/dashboard              → storage stats (admin)
  GET    /api/admin/shares                 → list all shares (admin)

  POST   /api/sharing/share                → share a session with another user
  GET    /api/sharing/inbox                → list sessions shared with me
  DELETE /api/sharing/{share_id}           → revoke a share
  POST   /api/sharing/{share_id}/apply     → generate CLAUDE.md content for a shared session
  GET    /api/sharing/{share_id}/bundle    → download the shared bundle

  GET    /admin/                           → web admin dashboard
  GET    /health                           → liveness check
"""

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import os

from . import auth, storage, git_backup, sharing, dashboard

app = FastAPI(title="Claude Sync Server", version="1.0.0")

# Mount admin web dashboard
app.include_router(dashboard.router, prefix="/admin")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Sessions — authenticated user scope
# ---------------------------------------------------------------------------

@app.post("/api/sessions/push")
async def push_session(
    project: str = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(auth.get_current_user),
):
    """Upload a bundle file. project = project folder name, filename = bundle filename."""
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 500 * 1024 * 1024:  # 500 MB hard limit
        raise HTTPException(status_code=413, detail="Bundle too large (max 500 MB)")

    path = storage.save_bundle(user["username"], project, filename, data)
    git_backup.backup_bundle(path, user["username"])

    return {
        "ok": True,
        "username": user["username"],
        "project": project,
        "filename": filename,
        "size": len(data),
    }


@app.get("/api/sessions")
def list_sessions(
    project: Optional[str] = None,
    user: dict = Depends(auth.get_current_user),
):
    """List all bundles for the authenticated user."""
    bundles = storage.list_bundles(user["username"], project=project)
    return {"bundles": bundles}


@app.get("/api/sessions/{prefix}/versions")
def list_versions(
    prefix: str,
    user: dict = Depends(auth.get_current_user),
):
    """List all versions of a specific session (by 8-char prefix)."""
    all_bundles = storage.list_bundles(user["username"])
    versions = [b for b in all_bundles if b["filename"].startswith(prefix)]
    if not versions:
        raise HTTPException(status_code=404, detail="No bundles found for this session")
    return {"versions": versions}


@app.get("/api/sessions/{prefix}")
def download_session(
    prefix: str,
    filename: Optional[str] = None,
    user: dict = Depends(auth.get_current_user),
):
    """Download a bundle. If filename is given, download that exact file; otherwise latest."""
    if filename:
        path = storage.get_bundle_by_name(user["username"], filename)
        if path is None:
            raise HTTPException(status_code=404, detail=f"Bundle '{filename}' not found")
    else:
        path = storage.get_latest_bundle(user["username"], prefix)
        if path is None:
            raise HTTPException(status_code=404, detail=f"No bundle found for prefix '{prefix}'")

    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="application/octet-stream",
    )


@app.delete("/api/sessions/{prefix}")
def delete_session(
    prefix: str,
    user: dict = Depends(auth.get_current_user),
):
    """Delete all bundles matching the session prefix."""
    count = storage.delete_bundle(user["username"], prefix)
    if count == 0:
        raise HTTPException(status_code=404, detail=f"No bundles found for prefix '{prefix}'")
    return {"ok": True, "deleted": count}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@app.post("/api/admin/users")
def create_user(
    username: str = Form(...),
    is_admin: bool = Form(False),
    admin: dict = Depends(auth.require_admin),
):
    """Create a new user and return their token. Token is shown only once."""
    try:
        token = auth.generate_token(username, is_admin=is_admin)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "ok": True,
        "username": username,
        "token": token,
        "warning": "Store this token safely — it will not be shown again.",
    }


@app.delete("/api/admin/users/{username}")
def delete_user(
    username: str,
    admin: dict = Depends(auth.require_admin),
):
    try:
        auth.delete_user(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "deleted": username}


@app.get("/api/admin/users")
def list_users(admin: dict = Depends(auth.require_admin)):
    return {"users": auth.list_users()}


@app.get("/api/admin/sessions")
def admin_list_sessions(admin: dict = Depends(auth.require_admin)):
    """List all bundles from all users."""
    return {"bundles": storage.list_all_bundles()}


@app.get("/api/admin/dashboard")
def admin_dashboard(admin: dict = Depends(auth.require_admin)):
    stats = storage.get_storage_stats()
    stats["total_mb"] = round(stats["total_bytes"] / (1024 * 1024), 2)
    return stats


@app.get("/api/admin/shares")
def admin_list_shares(admin: dict = Depends(auth.require_admin)):
    """List all shares (admin only)."""
    return {"shares": sharing.list_all_shares()}


# ---------------------------------------------------------------------------
# Sharing endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sharing/share")
def share_session_endpoint(
    session_prefix: str = Form(...),
    project: str = Form(...),
    share_with: str = Form(...),
    message: str = Form(""),
    user: dict = Depends(auth.get_current_user),
):
    """Share a session bundle with another user (or '*' for everyone)."""
    # Verify the session prefix exists for this user
    bundle = storage.get_latest_bundle(user["username"], session_prefix)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"No bundle found for prefix '{session_prefix}'")

    share_id = sharing.create_share(
        session_prefix=session_prefix,
        project=project,
        shared_by=user["username"],
        shared_with=share_with,
        message=message,
    )
    return {
        "ok": True,
        "share_id": share_id,
        "session_prefix": session_prefix,
        "shared_with": share_with,
    }


@app.get("/api/sharing/inbox")
def sharing_inbox(user: dict = Depends(auth.get_current_user)):
    """List sessions shared with the current user."""
    return {"shares": sharing.list_inbox(user["username"])}


@app.delete("/api/sharing/{share_id}")
def revoke_share(
    share_id: str,
    user: dict = Depends(auth.get_current_user),
):
    """Revoke a share. Owner or admin can revoke."""
    try:
        sharing.delete_share(share_id, user["username"], user["is_admin"])
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))
    return {"ok": True, "revoked": share_id}


@app.post("/api/sharing/{share_id}/apply")
def apply_share(
    share_id: str,
    user: dict = Depends(auth.get_current_user),
):
    """Return CLAUDE.md content for injecting a shared session's context."""
    share = sharing.get_share(share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")

    # Check access
    if share["shared_with"] not in (user["username"], "*") and not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this share")

    # Get bundle path from the owner's storage
    bundle_path = storage.get_latest_bundle(share["shared_by"], share["session_prefix"])
    if bundle_path is None:
        raise HTTPException(status_code=404, detail="Bundle not found on server")

    # Extract context from bundle
    import json as _json
    import gzip

    try:
        raw = bundle_path.read_bytes()
        # Try gzip first
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
        data = _json.loads(raw)
        messages = data.get("messages", [])
        # Last 5 human messages, truncated to 200 chars
        human_msgs = [
            m.get("content", "")[:200]
            for m in messages
            if m.get("role") == "human"
        ][-5:]
    except Exception:
        human_msgs = []

    from datetime import datetime
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    last_activity = share.get("created_at", "")[:19].replace("T", " ")

    lines = [
        "<!-- claude-sync:start -->",
        f"## Team Context (auto-updated: {now})",
        "",
        f"### {share['shared_by']} — {share['project']}",
        f"Last activity: {last_activity}",
    ]
    if human_msgs:
        lines.append("Recent messages:")
        for msg in human_msgs:
            lines.append(f"- {msg}")
    lines.append("<!-- claude-sync:end -->")

    return {"ok": True, "claude_md_content": "\n".join(lines), "share_id": share_id}


@app.get("/api/sharing/{share_id}/bundle")
def download_shared_bundle(
    share_id: str,
    user: dict = Depends(auth.get_current_user),
):
    """Download the bundle associated with a share."""
    share = sharing.get_share(share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")

    # Check access
    if share["shared_with"] not in (user["username"], "*") and not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this share")

    bundle_path = storage.get_latest_bundle(share["shared_by"], share["session_prefix"])
    if bundle_path is None:
        raise HTTPException(status_code=404, detail="Bundle not found")

    return FileResponse(
        path=str(bundle_path),
        filename=bundle_path.name,
        media_type="application/octet-stream",
    )
