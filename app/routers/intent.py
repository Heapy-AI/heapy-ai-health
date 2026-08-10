"""Intent 분류 API.

작성자: 김진우
"""
from fastapi import APIRouter, HTTPException

from app.core.state import state
from app.schemas.intent import IntentClassifyRequest, IntentClassifyResponse
from app.services.intent_classifier import INTENT_LABELS
from app.services.safety_guard import check_safety_guard


router = APIRouter(prefix="/intent", tags=["intent"])


@router.post("/classify", response_model=IntentClassifyResponse)
def classify_intent(request: IntentClassifyRequest) -> IntentClassifyResponse:
    """질문 임베딩을 한 번 계산하고 최상위 intent를 분류한다."""
    classifier = state.get("intent_classifier")
    if classifier is None:
        raise HTTPException(
            status_code=503,
            detail="학습된 intent 모델이 없어 분류기를 사용할 수 없습니다.",
        )

    resolver = state.get("query_resolver")
    resolution = (
        resolver.resolve(request.question)
        if callable(getattr(resolver, "resolve", None))
        else None
    )
    guard_result = check_safety_guard(request.question, resolution=resolution)
    if guard_result.triggered:
        # Guard 결과는 규칙이 명시적으로 확정한 라우팅이므로 confidence=1.0을 사용한다.
        probabilities = {label: 0.0 for label in INTENT_LABELS}
        probabilities["ignore"] = 1.0
        return IntentClassifyResponse(
            intent="ignore",
            confidence=1.0,
            probabilities=probabilities,
            uncertain=False,
            model_version=classifier.model_version,
            source="safety_guard",
            guard_triggered=True,
            guard_reason=guard_result.reason,
            matched_patterns=guard_result.matched_patterns,
        )

    vector_search = state["vector_search"]
    embedding = vector_search.embed_query(request.question)
    prediction = classifier.predict(embedding)
    return IntentClassifyResponse(
        intent=prediction.intent.value,
        confidence=prediction.confidence,
        probabilities=prediction.probabilities,
        uncertain=prediction.uncertain,
        model_version=prediction.model_version,
        source="linear_classifier",
        guard_triggered=False,
        guard_reason=None,
        matched_patterns=[],
    )
