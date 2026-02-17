"""
JWT Authentication middleware for Supabase tokens.

Validates the Authorization: Bearer <token> header on incoming requests.
The JWT is verified using the Supabase JWT secret (HMAC-HS256).

Public (unauthenticated) routes:
  - GET / , /health , /debug-db
  - OPTIONS (CORS preflight)
  
All other routes require a valid Supabase JWT token.
"""

from __future__ import annotations

import os
from typing import Optional

import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ── Config ──────────────────────────────────────────────────────────

def _get_jwt_secret() -> Optional[str]:
    """Get the Supabase JWT secret from environment."""
    return os.getenv("SUPABASE_JWT_SECRET")


def _allow_insecure_dev_auth() -> bool:
    """Explicit opt-in for local development when JWT secret is unavailable."""
    return os.getenv("ALLOW_INSECURE_DEV_AUTH", "false").strip().lower() == "true"


# ── Routes that don't require authentication ───────────────────────

PUBLIC_PATHS = {
    "/",
    "/health",
    "/debug-db",
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
    "/api/cotizacion/by-token",
    "/by-token",
)


# ── Bearer token extractor ─────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode and verify a Supabase JWT token."""
    secret = _get_jwt_secret()
    if not secret:
        if _allow_insecure_dev_auth():
            print("[AUTH] WARNING: SUPABASE_JWT_SECRET not set — insecure dev auth bypass enabled")
            return {"sub": "anonymous", "role": "anon"}
        raise HTTPException(
            status_code=500,
            detail="Configuración de autenticación inválida: falta SUPABASE_JWT_SECRET",
        )

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency that extracts and validates the JWT token.
    
    Usage in routers:
        @router.get("/protected")
        async def protected(user: dict = Depends(get_current_user)):
            ...
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Token de autenticación requerido")
    
    return _decode_token(credentials.credentials)


# ── Global Middleware ──────────────────────────────────────────────

class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Global middleware that enforces JWT authentication on all routes
    except public ones. 
    
    If SUPABASE_JWT_SECRET is not set, requests are blocked unless
    ALLOW_INSECURE_DEV_AUTH=true is explicitly configured.
    """

    async def dispatch(self, request: Request, call_next):
        # Always allow CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow public routes
        path = request.url.path.rstrip("/") or "/"
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # Check if JWT secret is configured
        secret = _get_jwt_secret()
        if not secret:
            if _allow_insecure_dev_auth():
                print("[AUTH] WARNING: SUPABASE_JWT_SECRET not set — insecure dev auth bypass enabled")
                return await call_next(request)
            return JSONResponse(
                status_code=500,
                content={"detail": "Configuración de autenticación inválida: falta SUPABASE_JWT_SECRET"},
            )

        # Extract Authorization header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Token de autenticación requerido"},
            )

        token = auth_header[7:]  # Strip "Bearer "

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
            # Attach user info to request state for downstream use
            request.state.user = payload
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token expirado. Por favor recarga la página."},
            )
        except jwt.InvalidTokenError as e:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Token inválido: {str(e)}"},
            )

        return await call_next(request)
