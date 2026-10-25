"""JWT 검증 (음성 서비스 공통) — rag-service/app/auth.py 와 같은 규칙

Java 인증서버가 발급한 토큰을 Bearer 헤더 또는 ACCESS_TOKEN 쿠키로 받는다.
비밀키는 코드에 두지 않고 환경변수 JWT_SECRET 을 쓴다 (dev.sh 가 auth-server/.env 값을 넘겨 준다).
"""
import os
from typing import Optional

from fastapi import Cookie, Header, HTTPException, status
from jose import JWTError, jwt

ALGORITHM = "HS256"
ISSUER = "simple-auth-server"   # Java JwtUtil.ISSUER 와 동일


def get_current_user(
    access_token: Optional[str] = Cookie(default=None, alias="ACCESS_TOKEN"),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """토큰이 없거나 만료·위조면 401, 비밀키가 없으면 503. 정상이면 {"id": ..., "username": ...}."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise unauthorized
        token = token.strip()
    else:
        token = access_token
    if not token:
        raise unauthorized
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is not configured (JWT_SECRET)")
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], issuer=ISSUER,
                             options={"require_exp": True, "require_sub": True, "require_iss": True})
    except (JWTError, TypeError, ValueError):
        raise unauthorized from None
    if not str(payload.get("sub") or "").strip():
        raise unauthorized
    return {"id": payload["sub"], "username": payload.get("username")}
