from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from services.auth_service import decode_jwt

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/login",
    "/auth/login",
    "/auth/callback",
    "/auth/gmail/callback",
    "/auth/logout",
    "/static",
    "/favicon.ico",
    "/privacy",
    "/terms",
    "/api/v1/health",
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path

        # Allow public paths
        for public in PUBLIC_PATHS:
            if path == public or path.startswith(public + "/") or path.startswith("/static"):
                return await call_next(request)

        # External API v1 routes — authenticate via API key
        if path.startswith("/api/v1/"):
            return await self._handle_api_key_auth(request, call_next)

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

    async def _handle_api_key_auth(self, request, call_next):
        # Accept Authorization: Bearer <key> or X-API-Key: <key>
        raw_key = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            raw_key = auth_header[7:].strip()
        if not raw_key:
            raw_key = request.headers.get("x-api-key", "").strip()

        if not raw_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "API key ausente. Use Authorization: Bearer <key> ou X-API-Key: <key>"},
            )

        from services.api_key_service import api_key_service

        result = api_key_service.validate_key(raw_key)
        if not result:
            return JSONResponse(
                status_code=401,
                content={"detail": "API key inválida ou revogada"},
            )

        # Inject user data in same format as JWT auth
        request.state.user = {
            "id": result["user_id"],
            "email": "api-key",
            "role": "user",
            "api_key_id": result["api_key_id"],
        }

        return await call_next(request)
