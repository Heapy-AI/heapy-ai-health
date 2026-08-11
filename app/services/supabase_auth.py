"""Supabase Auth REST API 연동 서비스.

작성자: 김진우
"""

from typing import Any

import requests


class SupabaseAuthConfigurationError(RuntimeError):
    """Supabase 인증 환경변수가 준비되지 않은 경우."""


class SupabaseAuthError(RuntimeError):
    """Supabase 인증 요청이 거부되거나 실패한 경우."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class SupabaseAuthService:
    """비밀번호 로그인과 사용자 토큰 검증을 Supabase에 위임한다."""

    def __init__(self, url: str, publishable_key: str) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key

    @property
    def configured(self) -> bool:
        """필수 Supabase 설정이 모두 존재하는지 반환한다."""
        return bool(self.url and self.publishable_key)

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        """이메일·비밀번호를 Supabase 세션으로 교환한다."""
        self._ensure_configured()
        return self._request(
            "POST",
            "/auth/v1/token?grant_type=password",
            json={"email": email, "password": password},
        )

    def sign_up(
        self,
        email: str,
        password: str,
        *,
        name: str,
        birth_date: str,
        sex: str,
    ) -> dict[str, Any]:
        """인증 계정과 프로필 생성에 필요한 메타데이터를 등록한다."""
        self._ensure_configured()
        return self._request(
            "POST",
            "/auth/v1/signup",
            json={
                "email": email,
                "password": password,
                "data": {
                    "name": name,
                    "birth_date": birth_date,
                    "sex": sex,
                },
            },
        )

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """일회성 refresh token으로 세션을 갱신한다."""
        self._ensure_configured()
        return self._request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": refresh_token},
        )

    def get_user(self, access_token: str) -> dict[str, Any]:
        """Auth 서버가 검증한 현재 사용자 정보를 반환한다."""
        self._ensure_configured()
        return self._request("GET", "/auth/v1/user", access_token=access_token)

    def sign_out(self, access_token: str) -> None:
        """현재 Supabase 세션을 로그아웃한다."""
        self._ensure_configured()
        self._request("POST", "/auth/v1/logout", access_token=access_token)

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise SupabaseAuthConfigurationError(
                "SUPABASE_URL과 SUPABASE_PUBLISHABLE_KEY를 설정해 주세요."
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        access_token: str = "",
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "apikey": self.publishable_key}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        try:
            response = requests.request(
                method,
                f"{self.url}{path}",
                headers=headers,
                json=json,
                timeout=(5, 15),
            )
        except requests.RequestException as exc:
            raise SupabaseAuthError(
                "인증 서버에 연결할 수 없습니다.", status_code=503
            ) from exc

        if not response.ok:
            payload = self._response_json(response)
            message = str(
                payload.get("msg")
                or payload.get("message")
                or payload.get("error_description")
                or "이메일 또는 비밀번호를 확인해 주세요."
            )
            raise SupabaseAuthError(message, status_code=response.status_code)
        if response.status_code == 204 or not response.content:
            return {}
        return self._response_json(response)

    @staticmethod
    def _response_json(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SupabaseAuthError(
                "인증 서버 응답을 해석할 수 없습니다.", status_code=502
            ) from exc
        return payload if isinstance(payload, dict) else {}
