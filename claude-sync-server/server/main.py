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

  GET    /health                           → liveness check
"""

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import os

from . import auth, storage, git_backup

app = FastAPI(title="Claude Sync Server", version="1.0.0")


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
def dashboard(admin: dict = Depends(auth.require_admin)):
    stats = storage.get_storage_stats()
    stats["total_mb"] = round(stats["total_bytes"] / (1024 * 1024), 2)
    return stats
