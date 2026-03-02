from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from config.database import get_db
from models.user import User
from services.auth_service import (
    get_google_auth_url,
    exchange_code,
    create_jwt,
    is_super_admin,
    get_gmail_connect_url,
    exchange_gmail_code,
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/login")
def login_page(request: Request):
    # If already authenticated, redirect to app
    token = request.cookies.get("session")
    if token:
        from services.auth_service import decode_jwt

        payload = decode_jwt(token)
        if payload:
            return RedirectResponse(url="/app")
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/auth/login")
def auth_login():
    url = get_google_auth_url()
    return RedirectResponse(url=url)


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", db: Session = Depends(get_db)):
    if not code:
        return RedirectResponse(url="/login?error=no_code")

    try:
        google_user = await exchange_code(code)
    except Exception as e:
        print(f"[Auth] Google exchange error: {e}")
        return RedirectResponse(url="/login?error=google_failed")

    email = google_user.get("email", "").lower()
    name = google_user.get("name", "")
    picture = google_user.get("picture", "")

    if not email:
        return RedirectResponse(url="/login?error=no_email")

    # Find user in DB
    user = db.query(User).filter(User.email == email).first()

    if not user:
        # Auto-create super admin
        if is_super_admin(email):
            user = User(
                email=email,
                name=name,
                picture=picture,
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[Auth] Super admin auto-created: {email}")
        else:
            return RedirectResponse(url="/login?error=not_allowed")

    if not user.is_active:
        return RedirectResponse(url="/login?error=inactive")

    # Update profile info and last login
    user.name = name
    user.picture = picture
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Create JWT and set cookie
    token = create_jwt(user.id, user.email, user.role)
    response = RedirectResponse(url="/app", status_code=302)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=72 * 3600,
    )
    return response


@router.get("/auth/gmail/connect")
def gmail_connect(request: Request):
    """Redirect logged-in user to Google consent for Gmail access."""
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse(url="/login")
    url = get_gmail_connect_url(state=str(user["id"]))
    return RedirectResponse(url=url)


@router.get("/auth/gmail/callback")
async def gmail_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback for Gmail connect. Creates/updates account."""
    if not code or not state:
        return RedirectResponse(url="/app#/settings?error=gmail_no_code")

    try:
        user_id = int(state)
    except (ValueError, TypeError):
        return RedirectResponse(url="/app#/settings?error=gmail_invalid_state")

    try:
        data = await exchange_gmail_code(code)
    except Exception as e:
        print(f"[Gmail Connect] Exchange error: {e}")
        return RedirectResponse(url="/app#/settings?error=gmail_exchange_failed")

    import json
    from models.account import Account

    gmail_email = data["email"].lower()
    oauth_token = json.dumps({
        "refresh_token": data["refresh_token"],
        "access_token": data["access_token"],
    })

    # Check if account already exists for this user+email (or legacy account without user_id)
    existing = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.email == gmail_email, Account.provider == "gmail")
        .first()
    )
    if not existing:
        # Check for legacy account without user_id
        existing = (
            db.query(Account)
            .filter(Account.user_id.is_(None), Account.email == gmail_email, Account.provider == "gmail")
            .first()
        )

    if existing:
        existing.oauth_token = oauth_token
        existing.name = data["name"] or existing.name
        existing.sync_status = "idle"
        existing.sync_error = None
        if not existing.user_id:
            existing.user_id = user_id
        db.commit()
        print(f"[Gmail Connect] Updated account for {gmail_email} (user_id={user_id})")
    else:
        account = Account(
            name=data["name"] or gmail_email.split("@")[0],
            email=gmail_email,
            provider="gmail",
            oauth_token=oauth_token,
            is_active=True,
            sync_status="idle",
            user_id=user_id,
        )
        db.add(account)
        db.commit()
        print(f"[Gmail Connect] Created account for {gmail_email} (user_id={user_id})")

    return RedirectResponse(url="/app#/sync")


@router.get("/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    user_data = getattr(request.state, "user", None)
    if not user_data:
        return JSONResponse(status_code=401, content={"detail": "Não autenticado"})

    # Fetch full user info from DB
    user = db.query(User).filter(User.id == user_data["id"]).first()
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Usuário não encontrado"})

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": user.role,
    }


@router.post("/auth/logout")
def auth_logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response
