"""최상위 Intent부터 응답까지 실행하는 통합 챗봇 API.

작성자: 김진우
"""
from fastapi import APIRouter, HTTPException

from app.core.state import state
from app.schemas.health_chatbot import (
    ChatRequest,
    ChatResponse,
    CombinedAnswerChunk,
    CombinedCitation,
)
from app.services.chat_orchestrator import (
    ChatOrchestrationResult,
    IntentClassifierUnavailableError,
    SearchUnavailableError,
)
from app.services.rag import cite


router = APIRouter(tags=["chat"])


def _to_answer_chunks(result: ChatOrchestrationResult) -> list[CombinedAnswerChunk]:
    """Gemini 문맥에 전달한 실제 Pinecone 청크를 응답 모델로 변환한다."""
    return [
        CombinedAnswerChunk(
            collection=str(document.metadata.get("collection", "unknown")),
            record_id=str(document.metadata.get("record_id", "")),
            score=float(document.metadata.get("score", 0.0) or 0.0),
            source=cite(document),
            text=document.page_content,
        )
        for document in result.documents
    ]


def _to_citations(result: ChatOrchestrationResult) -> list[CombinedCitation]:
    """검증된 인용 ID를 실제 Pinecone 청크와 연결한다."""
    citations: list[CombinedCitation] = []
    for citation_id in result.cited_chunk_ids:
        index = int(citation_id[1:]) - 1
        if index < 0 or index >= len(result.documents):
            continue
        document = result.documents[index]
        citations.append(
            CombinedCitation(
                citation_id=citation_id,
                collection=str(document.metadata.get("collection", "unknown")),
                record_id=str(document.metadata.get("record_id", "")),
                score=float(document.metadata.get("score", 0.0) or 0.0),
                source=cite(document),
                text=document.page_content,
            )
        )
    return citations


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Safety Guard와 Intent 분류를 거쳐 선택된 챗봇 경로를 실행한다."""
    orchestrator = state.get("chat_orchestrator")
    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="챗봇 오케스트레이터가 준비되지 않았습니다.",
        )

    try:
        result = orchestrator.answer(request.question)
    except IntentClassifierUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citations = _to_citations(result)
    sources = (
        sorted({citation.source for citation in citations})
        if result.grounded
        else []
    )
    return ChatResponse(
        question=request.question,
        intent=result.intent.value,
        confidence=result.confidence,
        probabilities=result.probabilities,
        uncertain=result.uncertain,
        model_version=result.model_version,
        intent_source=result.intent_source,
        guard_triggered=result.guard_triggered,
        guard_reason=result.guard_reason,
        matched_patterns=result.matched_patterns,
        answer=result.answer,
        sources=sources,
        grounded=result.grounded,
        chunks=_to_answer_chunks(result),
        citations=citations,
        verification_method=result.verification_method,
        verification_reason=result.verification_reason,
        grounding_errors=result.grounding_errors,
        unsupported_claims=result.unsupported_claims,
        searched_collections=result.searched_collections,
        failed_collections=result.failed_collections,
        personal_context_used=result.personal_context_used,
    )
