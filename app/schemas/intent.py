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
    """Linear/Softmax intent 분류 결과."""

    intent: str
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool
    model_version: str
