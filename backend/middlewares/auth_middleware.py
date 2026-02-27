from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from services.auth_service import decode_jwt

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/login",
    "/auth/login",
    "/auth/callback",
    "/auth/gmail/callback",
    "/auth/logout",
    "/static",
    "/favicon.ico",
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path

        # Allow public paths
        for public in PUBLIC_PATHS:
            if path == public or path.startswith(public + "/") or path.startswith("/static"):
                return await call_next(request)

        # Check JWT cookie
        token = request.cookies.get("session")
        if not token:
            # API requests get 401, page requests get redirected
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Não autenticado"},
                )
            return RedirectResponse(url="/login")

        payload = decode_jwt(token)
        if not payload:
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Sessão expirada"},
                )
            response = RedirectResponse(url="/login")
            response.delete_cookie("session")
            return response

        # Inject user data into request state
        request.state.user = {
            "id": payload["sub"],
            "email": payload["email"],
            "role": payload["role"],
        }

        return await call_next(request)
