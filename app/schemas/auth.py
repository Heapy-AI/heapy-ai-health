"""Supabase 인증 API 요청·응답 모델.

작성자: 김진우
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    """이메일과 비밀번호 로그인 요청."""

    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        """로그인 식별자로 사용할 이메일을 정규화한다."""
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("올바른 이메일을 입력해 주세요.")
        return normalized


class SignUpRequest(LoginRequest):
    """HEAPY 프로필을 포함하는 회원가입 요청."""

    password: str = Field(..., min_length=8, max_length=256)
    name: str = Field(..., min_length=1, max_length=50)
    birth_date: date
    sex: Literal["Male", "Female"]

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        """사용자 이름의 앞뒤 공백을 제거한다."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("이름을 입력해 주세요.")
        return normalized


class AuthUserResponse(BaseModel):
    """클라이언트에 노출할 최소 사용자 정보."""

    id: str
    email: str
    display_name: str = ""
    email_confirmation_required: bool = False
