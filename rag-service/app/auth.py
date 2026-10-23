"""JWT 검증 — 담당: 정지우

Java 인증서버가 발급한 ACCESS_TOKEN 쿠키를 같은 비밀키(JWT_SECRET)로 검증한다.
Java와 동일한 HS256·발급자를 사용하며 만료 시각과 사용자 식별자를 필수로 확인한다.
"""
import os
from typing import Optional

from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt

from rag.schema import ENV_JWT_SECRET

ALGORITHM = "HS256"
ISSUER = "simple-auth-server"   # Java JwtUtil.ISSUER 와 동일


def get_current_user(access_token: Optional[str] = Cookie(
    default=None,
    alias="ACCESS_TOKEN",
    description="Java 로그인 서버가 발급하는 HttpOnly 쿠키. localhost:8080/login에서 먼저 로그인하세요.",
)) -> dict:
    """토큰이 없거나 만료·위조면 401, 정상이면 {"sub": ..., "username": ...}."""
    if not access_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다 (ACCESS_TOKEN 없음).")
    secret = os.getenv(ENV_JWT_SECRET)
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "인증 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    try:
        payload = jwt.decode(
            access_token, secret, algorithms=[ALGORITHM], issuer=ISSUER,
            options={"require_exp": True, "require_sub": True, "require_iss": True},
        )
        if not payload["sub"].strip():
            raise JWTError("사용자 식별자 없음")
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "토큰이 만료되었거나 올바르지 않습니다.") from None
    return {"sub": payload.get("sub"), "username": payload.get("username")}
