# app/schemas/health_chatbot.py
"""건강관리 챗봇 요청/응답 Pydantic 모델 (FastAPI가 자동 검증·응답 형식 고정)"""
from pydantic import BaseModel, Field, field_validator

from app.core.config import COLLECTIONS


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
    searched_collections: list[str]
    failed_collections: list[str]
