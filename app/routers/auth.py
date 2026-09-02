"""Supabase Auth 기반 로그인·세션 API.

작성자: 김진우
"""

from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.core.config import (
    AUTH_COOKIE_SECURE,
    LIFESTYLE_CONTEXT_MAX_ROWS,
    LIFESTYLE_CONTEXT_TREND_MAX_ROWS,
    SUPABASE_PUBLISHABLE_KEY,
    SUPABASE_URL,
)
from app.schemas.auth import AuthUserResponse, LoginRequest, SignUpRequest
from app.services.supabase_conversation import (
    SupabaseConversationError,
    SupabaseConversationService,
)
from app.services.supabase_health_context import SupabaseHealthContextService
from app.services.supabase_lifestyle_context import SupabaseLifestyleContextService
from app.services.supabase_auth import (
    SupabaseAuthConfigurationError,
    SupabaseAuthError,
    SupabaseAuthService,
)


ACCESS_COOKIE = "heapy_access_token"
REFRESH_COOKIE = "heapy_refresh_token"
VERIFIED_USER_CACHE_TTL_SECONDS = 30.0
router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = SupabaseAuthService(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
conversation_service = SupabaseConversationService(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY,
)
health_context_service = SupabaseHealthContextService(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY,
)
lifestyle_context_service = SupabaseLifestyleContextService(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY,
    max_rows=LIFESTYLE_CONTEXT_MAX_ROWS,
    trend_max_rows=LIFESTYLE_CONTEXT_TREND_MAX_ROWS,
)
_verified_user_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_verified_user_cache_lock = RLock()


@dataclass(frozen=True)
class AuthenticatedSession:
    """검증된 Supabase 사용자와 원본 Access Token."""

    user: dict[str, Any]
    access_token: str


def _token_cache_key(access_token: str) -> str:
    """원본 토큰을 메모리 키로 남기지 않도록 해시한다."""
    return sha256(access_token.encode("utf-8")).hexdigest()


def _cache_verified_user(access_token: str, user: dict[str, Any]) -> None:
    """짧은 시간 동안 검증된 사용자 결과를 재사용한다.

    작성자: 김진우
    """
    if not access_token or not user:
        return
    now = monotonic()
    key = _token_cache_key(access_token)
    with _verified_user_cache_lock:
        expired_keys = [
            cache_key
            for cache_key, (expires_at, _) in _verified_user_cache.items()
            if expires_at <= now
        ]
        for expired_key in expired_keys:
            _verified_user_cache.pop(expired_key, None)
        _verified_user_cache[key] = (
            now + VERIFIED_USER_CACHE_TTL_SECONDS,
            dict(user),
        )


def _get_verified_user(access_token: str) -> dict[str, Any]:
    """캐시를 우선 사용하고 필요할 때만 Supabase Auth에 재검증한다."""
    key = _token_cache_key(access_token)
    now = monotonic()
    with _verified_user_cache_lock:
        cached = _verified_user_cache.get(key)
        if cached and cached[0] > now:
            return dict(cached[1])
        _verified_user_cache.pop(key, None)
    user = auth_service.get_user(access_token)
    _cache_verified_user(access_token, user)
    return user


def _drop_verified_user(access_token: str) -> None:
    """로그아웃 토큰의 사용자 검증 캐시를 즉시 제거한다."""
    if not access_token:
        return
    with _verified_user_cache_lock:
        _verified_user_cache.pop(_token_cache_key(access_token), None)


def _raise_http_error(error: Exception) -> None:
    """인증 도메인 오류를 일관된 HTTP 오류로 변환한다."""
    if isinstance(error, SupabaseAuthConfigurationError):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, SupabaseAuthError):
        status_code = 401 if error.status_code in {400, 401, 403} else error.status_code
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    raise error


def _set_session_cookies(response: Response, session: dict[str, Any]) -> None:
    """Supabase 세션을 JavaScript가 읽을 수 없는 쿠키로 저장한다."""
    access_token = str(session.get("access_token", ""))
    refresh_token = str(session.get("refresh_token", ""))
    expires_in = max(int(session.get("expires_in", 3600) or 3600), 60)
    if not access_token or not refresh_token:
        raise HTTPException(status_code=502, detail="인증 세션 토큰이 누락되었습니다.")
    user = session.get("user") or {}
    if isinstance(user, dict):
        _cache_verified_user(access_token, user)
    cookie_options = {
        "httponly": True,
        "secure": AUTH_COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=expires_in, **cookie_options)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=60 * 60 * 24 * 30,
        **cookie_options,
    )


def _to_user(
    user: dict[str, Any],
    *,
    display_name: str = "",
    email_confirmation_required: bool = False,
) -> AuthUserResponse:
    """Supabase 사용자 객체에서 화면에 필요한 값만 선택한다."""
    metadata = user.get("user_metadata") or {}
    resolved_name = display_name or str(
        metadata.get("display_name")
        or metadata.get("full_name")
        or metadata.get("name")
        or ""
    )
    return AuthUserResponse(
        id=str(user.get("id", "")),
        email=str(user.get("email", "")),
        display_name=resolved_name,
        email_confirmation_required=email_confirmation_required,
    )


def optional_current_session(
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> AuthenticatedSession | None:
    """Supabase 설정 환경에서는 유효한 로그인 사용자를 요구한다.

    설정이 없는 로컬 개발·단위 테스트 환경은 기존 익명 API 동작을 유지한다.
    """
    if not auth_service.configured:
        return None
    if not access_token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    try:
        user = _get_verified_user(access_token)
        return AuthenticatedSession(user=user, access_token=access_token)
    except (SupabaseAuthConfigurationError, SupabaseAuthError) as error:
        _raise_http_error(error)
    return None


def optional_current_user(
    session: AuthenticatedSession | None = Depends(optional_current_session),
) -> dict[str, Any] | None:
    """기존 라우터 호환을 위해 검증된 사용자 객체만 반환한다."""
    return session.user if session else None


def require_current_session(
    session: AuthenticatedSession | None = Depends(optional_current_session),
) -> AuthenticatedSession:
    """Supabase 설정과 로그인이 모두 준비된 세션을 반환한다."""
    if session is None:
        raise HTTPException(status_code=503, detail="Supabase 인증 설정이 필요합니다.")
    return session


@router.post("/signup", response_model=AuthUserResponse)
def signup(request: SignUpRequest, response: Response) -> AuthUserResponse:
    """Auth 사용자와 동일 UUID의 HEAPY 프로필을 생성한다."""
    try:
        session = auth_service.sign_up(
            request.email,
            request.password,
            name=request.name,
            birth_date=request.birth_date.isoformat(),
            sex=request.sex,
        )
        access_token = str(session.get("access_token") or "")
        refresh_token = str(session.get("refresh_token") or "")
        confirmation_required = not (access_token and refresh_token)
        if not confirmation_required:
            _set_session_cookies(response, session)
        return _to_user(
            session.get("user") or {},
            display_name=request.name,
            email_confirmation_required=confirmation_required,
        )
    except (SupabaseAuthConfigurationError, SupabaseAuthError) as error:
        _raise_http_error(error)
    raise HTTPException(status_code=500, detail="회원가입 처리에 실패했습니다.")


@router.post("/login", response_model=AuthUserResponse)
def login(request: LoginRequest, response: Response) -> AuthUserResponse:
    """Supabase 이메일·비밀번호 로그인 후 보안 쿠키를 발급한다."""
    try:
        session = auth_service.sign_in(request.email, request.password)
        _set_session_cookies(response, session)
        return _to_user(session.get("user") or {})
    except (SupabaseAuthConfigurationError, SupabaseAuthError) as error:
        _raise_http_error(error)
    raise HTTPException(status_code=500, detail="로그인 처리에 실패했습니다.")


@router.get("/me", response_model=AuthUserResponse)
def me(session: AuthenticatedSession = Depends(require_current_session)) -> AuthUserResponse:
    """현재 로그인 사용자를 반환한다."""
    try:
        profile = conversation_service.get_profile(
            session.access_token,
            str(session.user.get("id", "")),
        )
    except SupabaseConversationError:
        profile = None
    return _to_user(
        session.user,
        display_name=str((profile or {}).get("name", "")),
    )


@router.post("/refresh", response_model=AuthUserResponse)
def refresh_session(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> AuthUserResponse:
    """만료된 access token과 refresh token을 함께 교체한다."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="다시 로그인해 주세요.")
    try:
        session = auth_service.refresh(refresh_token)
        _set_session_cookies(response, session)
        return _to_user(session.get("user") or {})
    except (SupabaseAuthConfigurationError, SupabaseAuthError) as error:
        _raise_http_error(error)
    raise HTTPException(status_code=500, detail="세션 갱신에 실패했습니다.")


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> Response:
    """Supabase 세션과 브라우저 인증 쿠키를 제거한다."""
    if access_token and auth_service.configured:
        _drop_verified_user(access_token)
        try:
            auth_service.sign_out(access_token)
        except SupabaseAuthError:
            pass
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
    response.status_code = 204
    return response
