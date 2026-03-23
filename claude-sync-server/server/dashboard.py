"""
dashboard.py — Admin web dashboard (HTML, Jinja2).

Routes:
  GET  /admin/              → dashboard stats page
  GET  /admin/users         → users table
  GET  /admin/sessions      → all sessions table
  GET  /admin/shares        → shares table
  POST /admin/users/create  → create user form action
  POST /admin/users/{u}/delete → delete user form action
  POST /admin/shares/{id}/revoke → revoke share form action
  GET  /admin/login         → login page
  POST /admin/login         → authenticate (sets cookie)

Auth: cookie `admin_token` checked against the user store (must be admin).
"""

import os
from pathlib import Path
from fastapi import APIRouter, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from . import auth, storage, sharing

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _resolve_admin_cookie(admin_token: Optional[str]) -> Optional[dict]:
    """Return user dict if token is valid and is_admin, else None."""
    if not admin_token:
        return None
    result = auth._resolve_user(admin_token)
    if result is None:
        return None
    username, is_admin = result
    if not is_admin:
        return None
    return {"username": username, "is_admin": True}


def _require_admin(request: Request):
    """Return (admin_user, redirect_response). One of them will be None."""
    token = request.cookies.get("admin_token")
    user = _resolve_admin_cookie(token)
    if user is None:
        return None, RedirectResponse("/admin/login", status_code=302)
    return user, None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, token: str = Form(...)):
    result = auth._resolve_user(token)
    if result is None or not result[1]:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid token or not an admin."},
            status_code=401,
        )
    response = RedirectResponse("/admin/", status_code=302)
    response.set_cookie("admin_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    stats = storage.get_storage_stats()
    stats["total_mb"] = round(stats["total_bytes"] / (1024 * 1024), 2)
    stats["total_shares"] = len(sharing.list_all_shares())

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "active": "dashboard"},
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    users = auth.list_users()
    return templates.TemplateResponse(
        "users.html",
        {"request": request, "users": users, "active": "users",
         "error": None, "success": None, "new_token": None},
    )


@router.post("/users/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    username: str = Form(...),
    is_admin: Optional[str] = Form(None),
):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    users = auth.list_users()
    new_token = None
    error = None
    success = None

    try:
        admin_flag = is_admin == "true"
        new_token = auth.generate_token(username, is_admin=admin_flag)
        success = f"User '{username}' created successfully."
        users = auth.list_users()
    except ValueError as e:
        error = str(e)

    return templates.TemplateResponse(
        "users.html",
        {"request": request, "users": users, "active": "users",
         "error": error, "success": success, "new_token": new_token},
    )


@router.post("/users/{username}/delete")
async def delete_user_form(request: Request, username: str):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    try:
        auth.delete_user(username)
    except ValueError:
        pass
    return RedirectResponse("/admin/users", status_code=302)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@router.get("/sessions", response_class=HTMLResponse)
def sessions_page(request: Request):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    bundles = storage.list_all_bundles()
    return templates.TemplateResponse(
        "sessions.html",
        {"request": request, "bundles": bundles, "active": "sessions"},
    )


# ---------------------------------------------------------------------------
# Shares
# ---------------------------------------------------------------------------

@router.get("/shares", response_class=HTMLResponse)
def shares_page(request: Request):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    all_shares = sharing.list_all_shares()
    return templates.TemplateResponse(
        "shares.html",
        {"request": request, "shares": all_shares, "active": "shares"},
    )


@router.post("/shares/{share_id}/revoke")
async def revoke_share_form(request: Request, share_id: str):
    user, redirect = _require_admin(request)
    if redirect:
        return redirect

    try:
        sharing.delete_share(share_id, user["username"], is_admin=True)
    except ValueError:
        pass
    return RedirectResponse("/admin/shares", status_code=302)
