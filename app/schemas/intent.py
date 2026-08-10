"""Intent 분류 API 요청·응답 모델.

작성자: 김진우
"""
from pydantic import BaseModel, Field, field_validator


class IntentClassifyRequest(BaseModel):
    """분류할 사용자 질문."""

    question: str = Field(..., description="intent를 분류할 사용자 질문")

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("질문은 비어 있을 수 없습니다.")
        return normalized


class IntentClassifyResponse(BaseModel):
    """Linear/Softmax Intent와 독립적으로 계산한 안전 정책 결과."""

    intent: str
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool
    model_version: str
    source: str = "linear_classifier"
    guard_triggered: bool = False
    guard_reason: str | None = None
    matched_patterns: list[str] = Field(default_factory=list)
    risk_level: str = "normal"
    restricted_actions: list[str] = Field(default_factory=list)
    response_policy: str = "standard_grounded"
    emergency: bool = False
