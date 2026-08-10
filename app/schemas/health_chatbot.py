# app/schemas/health_chatbot.py
"""건강관리 챗봇 요청/응답 Pydantic 모델 (FastAPI가 자동 검증·응답 형식 고정)"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import (
    CHAT_HISTORY_MAX_CHARS,
    CHAT_HISTORY_MAX_TURNS,
    COLLECTIONS,
    CONVERSATION_SUMMARY_MAX_CHARS,
)


# ── /search, /ask 공용 요청 모델 ──
class AskRequest(BaseModel):
    question: str = Field(..., description="건강 정보에 대한 질문")
    collection: str = Field(..., description=f"검색할 지식베이스 (사용 가능: {list(COLLECTIONS)})")

    @field_validator("collection")
    @classmethod
    def _check_collection(cls, v: str) -> str:
        if v not in COLLECTIONS:
            raise ValueError(f"알 수 없는 컬렉션입니다: '{v}' (사용 가능: {list(COLLECTIONS)})")
        return v


# ── 검색된 청크 1건 ──
class SearchHit(BaseModel):
    source: str                              # 출처 표기('라벨 · URL')
    text: str                                # 검색된 청크 본문(앞 120자 미리보기)


# ── /search 응답 ──
class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


# ── /ask 응답 ──
class AskResponse(BaseModel):
    answer: str                              # 지식베이스 근거 답변(없으면 "지식베이스에 근거 없음")
    sources: list[str]                       # 출처 목록(["AIHub 전문 의학지식 데이터 · https://...", ...])
    grounded: bool                           # 근거로 답했는지(False면 회피)


class CombinedAskRequest(BaseModel):
    """서버가 설정된 모든 namespace를 검색하는 요청."""

    question: str = Field(..., min_length=1, description="건강 정보에 대한 질문")


class CombinedSearchHit(BaseModel):
    """다중 컬렉션 검색 결과 한 건."""

    collection: str
    score: float
    source: str
    text: str


class CombinedSearchResponse(BaseModel):
    """병렬 검색 결과와 namespace별 처리 상태."""

    query: str
    hits: list[CombinedSearchHit]
    searched_collections: list[str]
    failed_collections: list[str]


class CombinedAnswerChunk(BaseModel):
    """답변 생성 문맥에 실제로 전달된 최종 청크."""

    collection: str
    record_id: str
    score: float
    source: str
    text: str


class CombinedCitation(CombinedAnswerChunk):
    """답변 본문이 실제로 인용하고 검증한 청크."""

    citation_id: str


class CombinedAskResponse(AskResponse):
    """병렬 검색 기반 답변, 최종 청크와 namespace별 처리 상태."""

    chunks: list[CombinedAnswerChunk]
    citations: list[CombinedCitation]
    verification_method: str
    verification_reason: str
    grounding_errors: list[str]
    unsupported_claims: list[str]
    grounding_plan: dict | None
    audit_status: str
    audit_summary: str
    searched_collections: list[str]
    failed_collections: list[str]


class ChatTurn(BaseModel):
    """클라이언트가 보관하는 직전 대화 한 턴.

    서버는 대화를 저장하지 않는다. 멀티턴 문맥은 요청마다 클라이언트가 실어 보낸다.
    """

    role: Literal["user", "assistant"] = Field(..., description="발화 주체")
    content: str = Field(..., description="발화 내용")

    @field_validator("content")
    @classmethod
    def _trim_content(cls, value: str) -> str:
        return value.strip()[:CHAT_HISTORY_MAX_CHARS]


class ChatRequest(BaseModel):
    """최상위 Intent부터 자동 분기하는 통합 챗봇 요청."""

    question: str = Field(..., min_length=1, description="사용자 질문")
    history: list[ChatTurn] = Field(
        default_factory=list,
        description=(
            "직전 대화(오래된 순). 후속 질문의 대명사·생략을 해소하는 데만 사용하며 "
            f"최근 {CHAT_HISTORY_MAX_TURNS}턴까지 반영합니다."
        ),
    )

    summary: str = Field(
        default="",
        description=(
            "창 밖으로 밀려난 이전 대화의 요약. 서버가 응답으로 돌려준 값을 "
            "클라이언트가 보관했다가 다음 요청에 그대로 실어 보냅니다."
        ),
    )

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("질문은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("summary")
    @classmethod
    def _limit_summary(cls, value: str) -> str:
        return value.strip()[:CONVERSATION_SUMMARY_MAX_CHARS]

    @field_validator("history")
    @classmethod
    def _limit_history(cls, value: list[ChatTurn]) -> list[ChatTurn]:
        """빈 발화를 버리고 최근 N턴만 남긴다."""
        turns = [turn for turn in value if turn.content]
        return turns[-CHAT_HISTORY_MAX_TURNS:]


class GroundingPlanFactResponse(BaseModel):
    """선검증된 단일 근거 사실."""

    statement: str
    cited_chunk_ids: list[str]


class GroundingPlanResponse(BaseModel):
    """최종 답변 스트리밍 전에 승인된 근거 계획."""

    answerable: bool
    facts: list[GroundingPlanFactResponse]
    reason: str


class ChatResponse(BaseModel):
    """Intent 분류와 선택된 처리 경로의 통합 응답."""

    question: str
    intent: str
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool
    model_version: str
    intent_source: str
    guard_triggered: bool
    guard_reason: str | None
    matched_patterns: list[str]
    answer: str
    sources: list[str]
    grounded: bool | None
    chunks: list[CombinedAnswerChunk]
    citations: list[CombinedCitation]
    verification_method: str
    verification_reason: str
    grounding_errors: list[str]
    unsupported_claims: list[str]
    grounding_plan: GroundingPlanResponse | None
    audit_status: str
    audit_summary: str
    searched_collections: list[str]
    failed_collections: list[str]
    personal_context_used: bool
    original_question: str = ""
    search_question: str = ""
    query_rewritten: bool = False
    rewrite_reason: str = ""
    conversation_summary: str = ""
    summary_updated: bool = False
