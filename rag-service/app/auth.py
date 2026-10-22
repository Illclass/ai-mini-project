"""JWT 검증 — 담당: 정지우

Java 인증서버가 발급한 ACCESS_TOKEN 쿠키를 같은 비밀키(JWT_SECRET)로 검증한다.
(voice-service/app/main.py 의 get_current_user() 와 같은 방식으로 넣은 임시 버전 — 검토는 API 담당)
"""
import os
from typing import Optional

from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt

from rag.schema import ENV_JWT_SECRET

ALGORITHM = "HS256"
ISSUER = "simple-auth-server"   # Java JwtUtil.ISSUER 와 동일


def get_current_user(access_token: Optional[str] = Cookie(default=None, alias="ACCESS_TOKEN")) -> dict:
    """토큰이 없거나 만료·위조면 401, 정상이면 {"sub": ..., "username": ...}."""
    secret = os.getenv(ENV_JWT_SECRET)
    if not secret:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "JWT_SECRET 이 설정되지 않았습니다.")
    if not access_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다 (ACCESS_TOKEN 없음).")
    try:
        payload = jwt.decode(access_token, secret, algorithms=[ALGORITHM], issuer=ISSUER)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "토큰이 만료되었거나 올바르지 않습니다.")
    return {"sub": payload.get("sub"), "username": payload.get("username")}
