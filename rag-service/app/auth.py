"""JWT 검증 — 담당: 정지우

Java 인증서버가 발급한 ACCESS_TOKEN 쿠키를 같은 비밀키(JWT_SECRET)로 검증한다.
참고: voice-service/app/main.py 의 get_current_user()
"""
from typing import Optional

from fastapi import Cookie


def get_current_user(access_token: Optional[str] = Cookie(default=None, alias="ACCESS_TOKEN")) -> dict:
    """토큰이 없거나 만료·위조면 401, 정상이면 {"sub": ..., "username": ...}."""
    # TODO: jose.jwt.decode(access_token, JWT_SECRET, algorithms=["HS256"], issuer="simple-auth-server")
    raise NotImplementedError
