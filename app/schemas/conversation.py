"""Supabase 챗봇 대화 세션 API 모델.

작성자: 김진우
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConversationSessionResponse(BaseModel):
    """사용자 대화 세션 요약."""

    session_id: str
    title: str
    summary: str = ""
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(BaseModel):
    """대화 세션의 메시지 한 건."""

    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    """선택한 세션과 전체 메시지."""

    session: ConversationSessionResponse
    messages: list[ConversationMessageResponse]

