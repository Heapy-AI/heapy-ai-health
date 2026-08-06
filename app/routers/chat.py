"""최상위 Intent부터 응답까지 실행하는 통합 챗봇 API.

작성자: 김진우
"""
import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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


class _CitationLabelStreamFilter:
    """토큰 경계를 걸친 검증용 인용 라벨을 표시 스트림에서 제거한다.

    작성자: 김진우
    """

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        """새 토큰을 받아 사용자에게 표시 가능한 문자열만 반환한다."""
        output: list[str] = []
        for character in text:
            if not self._pending:
                if character == "[":
                    self._pending = character
                else:
                    output.append(character)
                continue

            self._pending += character
            if self._is_complete_label(self._pending):
                self._pending = ""
            elif not self._is_partial_label(self._pending):
                output.append(self._pending)
                self._pending = ""
        return "".join(output)

    def flush(self) -> str:
        """인용 라벨이 아니었던 마지막 대기 문자열을 반환한다."""
        pending = self._pending
        self._pending = ""
        return pending

    @staticmethod
    def _is_partial_label(value: str) -> bool:
        if value in {"[", "[C"}:
            return True
        return value.startswith("[C") and value[2:].isdigit()

    @staticmethod
    def _is_complete_label(value: str) -> bool:
        return (
            value.startswith("[C")
            and value.endswith("]")
            and value[2:-1].isdigit()
        )


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


def _to_chat_response(
    question: str,
    result: ChatOrchestrationResult,
) -> ChatResponse:
    """오케스트레이션 결과를 동기·스트리밍 공통 API 응답으로 변환한다.

    작성자: 김진우
    """
    citations = _to_citations(result)
    sources = (
        sorted({citation.source for citation in citations})
        if result.grounded
        else []
    )
    return ChatResponse(
        question=question,
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
        grounding_plan=result.grounding_plan,
        audit_status=result.audit_status,
        audit_summary=result.audit_summary,
        searched_collections=result.searched_collections,
        failed_collections=result.failed_collections,
        personal_context_used=result.personal_context_used,
    )


def _sse_event(event: str, data: dict) -> str:
    """한 건의 JSON 데이터를 SSE 이벤트 문자열로 직렬화한다.

    작성자: 김진우
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


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

    return _to_chat_response(request.question, result)


@router.post("/chat/stream")
def stream_chat(request: ChatRequest) -> StreamingResponse:
    """LLM 토큰과 검증 완료 응답을 SSE로 순차 전송한다.

    작성자: 김진우
    """
    orchestrator = state.get("chat_orchestrator")
    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="챗봇 오케스트레이터가 준비되지 않았습니다.",
        )

    def generate_events() -> Iterator[str]:
        label_filter = _CitationLabelStreamFilter()
        try:
            for stream_event in orchestrator.stream_answer(request.question):
                if stream_event.event == "token":
                    display_text = label_filter.feed(stream_event.text)
                    if display_text:
                        yield _sse_event("token", {"text": display_text})
                    continue
                if stream_event.result is None:
                    continue
                trailing_text = label_filter.flush()
                if trailing_text:
                    yield _sse_event("token", {"text": trailing_text})
                response = _to_chat_response(
                    request.question,
                    stream_event.result,
                )
                yield _sse_event(
                    "complete",
                    response.model_dump(mode="json"),
                )
        except (IntentClassifierUnavailableError, SearchUnavailableError) as exc:
            yield _sse_event("error", {"message": str(exc)})
        except Exception:
            yield _sse_event(
                "error",
                {"message": "답변 스트리밍 중 오류가 발생했습니다."},
            )

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
