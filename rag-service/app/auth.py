"""JWT 검증 — 담당: 정지우

Java가 발급한 Bearer JWT를 검증하고 기존 ACCESS_TOKEN 쿠키도 호환한다.
Java와 동일한 HS256·발급자를 사용하며 만료 시각과 사용자 식별자를 필수로 확인한다.
"""
import logging
import os
from time import perf_counter
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from rag.schema import ENV_JWT_SECRET

pipeline_log = logging.getLogger("chembridge.pipeline")

ALGORITHM = "HS256"
ISSUER = "simple-auth-server"   # Java JwtUtil.ISSUER 와 동일
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="Java POST /api/login 응답의 accessToken을 입력하세요.",
)


def get_current_user(
    access_token: Optional[str] = Cookie(
        default=None,
        alias="ACCESS_TOKEN",
        description="기존 클라이언트용 HttpOnly 쿠키. Bearer 헤더가 있으면 해당 헤더를 우선 검증합니다.",
    ),
    authorization: Optional[str] = Header(default=None, include_in_schema=False),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """토큰이 없거나 만료·위조면 401, 정상이면 {"sub": ..., "username": ...}.

    기록하는 시간은 이 함수의 인증 처리이며, 앞선 HTTPBearer 헤더 파싱은 제외한다.
    """
    started = perf_counter()
    event = {"stage": "authentication", "status": "error", "reason": "authentication_error"}
    try:
        unauthorized = HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "토큰이 없거나 만료되었거나 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if authorization is not None:
            if bearer is None:
                event["reason"] = "invalid_token"
                raise unauthorized
            token = bearer.credentials
        else:
            token = access_token
        if not token:
            event["reason"] = "authentication_required"
            raise unauthorized
        secret = os.getenv(ENV_JWT_SECRET)
        if not secret:
            event["reason"] = "auth_configuration_unavailable"
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "인증 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        try:
            payload = jwt.decode(
                token, secret, algorithms=[ALGORITHM], issuer=ISSUER,
                options={"require_exp": True, "require_sub": True, "require_iss": True},
            )
            if not payload["sub"].strip():
                raise JWTError("사용자 식별자 없음")
        except (JWTError, TypeError, ValueError) as exc:
            event.update(reason="invalid_token", exception_type=type(exc).__name__)
            raise unauthorized from None
        event.update(status="ok", reason="authenticated")
        return {"sub": payload.get("sub"), "username": payload.get("username")}
    except Exception as exc:
        event.setdefault("exception_type", type(exc).__name__)
        raise
    finally:
        event["duration_ms"] = (perf_counter() - started) * 1000
        pipeline_log.info("pipeline_stage", extra={"pipeline_event": event})
