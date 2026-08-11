"""Intent 분류 API.

작성자: 김진우
"""
from fastapi import APIRouter, HTTPException

from app.core.state import state
from app.schemas.intent import IntentClassifyRequest, IntentClassifyResponse
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

    vector_search = state["vector_search"]
    embedding = vector_search.embed_query(request.question)
    prediction = classifier.predict(embedding)
    guard_result = check_safety_guard(request.question)
    return IntentClassifyResponse(
        intent=prediction.intent.value,
        confidence=prediction.confidence,
        probabilities=prediction.probabilities,
        uncertain=prediction.uncertain,
        model_version=prediction.model_version,
        source="linear_classifier",
        guard_triggered=guard_result.triggered,
        guard_reason=guard_result.reason,
        matched_patterns=guard_result.matched_patterns,
        risk_level=guard_result.risk_level.value,
        restricted_actions=guard_result.restricted_actions,
        response_policy=guard_result.response_policy,
        emergency=guard_result.emergency,
    )
