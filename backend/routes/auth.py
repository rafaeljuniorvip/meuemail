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
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/login")
def login_page(request: Request):
    # If already authenticated, redirect to home
    token = request.cookies.get("session")
    if token:
        from services.auth_service import decode_jwt

        payload = decode_jwt(token)
        if payload:
            return RedirectResponse(url="/")
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
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=72 * 3600,
    )
    return response


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
