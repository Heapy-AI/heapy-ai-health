"""최상위 Intent부터 응답까지 실행하는 통합 챗봇 API.

작성자: 김진우
"""
import json
import re
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import CHAT_HISTORY_MAX_TURNS
from app.core.state import state
from app.routers.auth import (
    AuthenticatedSession,
    conversation_service,
    health_context_service,
    optional_current_session,
)
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
from app.services.supabase_conversation import SupabaseConversationError


router = APIRouter(tags=["chat"])


PROGRESS_MESSAGES = {
    "load_conversation": "이전 대화 내용을 불러오는 중입니다",
    "prepare_query": "질문과 의료용어를 정리하는 중입니다",
    "classify_intent": "질문의 유형과 안전 기준을 확인하는 중입니다",
    "load_health_context": "관련 건강검진 결과를 확인하는 중입니다",
    "search_evidence": "관련 건강정보 근거를 찾는 중입니다",
    "generate_answer": "답변을 생성하는 중입니다",
    "verify_answer": "최종 결과를 확인하는 중입니다",
    "summarize_conversation": "대화 내용을 요약하는 중입니다",
    "save_conversation": "대화 내용을 저장하는 중입니다",
}


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
        if value == "[":
            return True
        return bool(
            re.fullmatch(r"\[[Cc]\d*(?:\s*,\s*[Cc]?\d*)*\s*", value)
        )

    @staticmethod
    def _is_complete_label(value: str) -> bool:
        return bool(
            re.fullmatch(r"\[[Cc]\d+(?:\s*,\s*[Cc]?\d+)*\s*]", value)
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
    session_id: str = "",
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
        session_id=session_id,
        intent=result.intent.value,
        confidence=result.confidence,
        probabilities=result.probabilities,
        uncertain=result.uncertain,
        model_version=result.model_version,
        intent_source=result.intent_source,
        guard_triggered=result.guard_triggered,
        guard_reason=result.guard_reason,
        matched_patterns=result.matched_patterns,
        risk_level=result.risk_level,
        restricted_actions=result.restricted_actions,
        response_policy=result.response_policy,
        emergency=result.emergency,
        answer=result.answer,
        sources=sources,
        grounded=result.grounded,
        chunks=_to_answer_chunks(result),
        citations=citations,
        verification_method=result.verification_method,
        verification_reason=result.verification_reason,
        grounding_errors=result.grounding_errors,
        unsupported_claims=result.unsupported_claims,
        evidence_status=result.evidence_status,
        retrieval_assessment=result.retrieval_assessment,
        audit_status=result.audit_status,
        audit_summary=result.audit_summary,
        unanswered_items=result.unanswered_items,
        safety_violations=result.safety_violations,
        searched_collections=result.searched_collections,
        failed_collections=result.failed_collections,
        personal_context_used=result.personal_context_used,
        original_question=result.original_question or question,
        standalone_question=result.standalone_question or question,
        resolved_query=result.resolved_query or question,
        query_rewritten=result.query_rewritten,
        rewrite_reason=result.rewrite_reason,
        rewrite_error=result.rewrite_error,
        is_follow_up=result.is_follow_up,
        current_topic=result.current_topic,
        inherited_target=result.inherited_target,
        personal_context_required=result.personal_context_required,
        resolved_terms=result.resolved_terms,
        resolution_status=result.resolution_status,
        resolution_error=result.resolution_error,
        query_confirmation=result.query_confirmation,
        confirmation_question=result.confirmation_question,
        confirmation_id=result.confirmation_id,
        conversation_summary=result.conversation_summary,
        summary_updated=result.summary_updated,
        summary_reason=result.summary_reason,
    )


def _sse_event(event: str, data: dict) -> str:
    """한 건의 JSON 데이터를 SSE 이벤트 문자열로 직렬화한다.

    작성자: 김진우
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _conversation_context(
    request: ChatRequest,
    session: AuthenticatedSession | None,
) -> tuple[str, list, str]:
    """인증 환경에서는 DB를 멀티턴 문맥의 단일 진실 공급원으로 사용한다.

    작성자: 김진우
    """
    if session is None:
        return "", request.history, request.summary
    try:
        if request.session_id:
            session_row = conversation_service.get_session(
                session.access_token,
                request.session_id,
            )
        else:
            session_row = conversation_service.create_session(
                session.access_token,
                str(session.user.get("id", "")),
            )
        session_id = str(session_row.get("session_id", ""))
        messages = conversation_service.get_messages(
            session.access_token,
            session_id,
            limit=CHAT_HISTORY_MAX_TURNS,
        )
        history = [
            {"role": row.get("role", ""), "content": row.get("content", "")}
            for row in messages
        ]
        return session_id, history, str(session_row.get("summary") or "")
    except SupabaseConversationError as error:
        status_code = error.status_code if error.status_code in {400, 404, 503} else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error


def _personal_context_loader(session: AuthenticatedSession | None):
    """현재 로그인 사용자의 질문 관련 검진 컨텍스트 로더를 만든다.

    작성자: 김진우
    """
    if session is None:
        return None
    user_id = str(session.user.get("id", ""))

    def load(question: str, resolved_terms: list[dict]) -> str | None:
        context = health_context_service.get_relevant_context(
            session.access_token,
            user_id,
            question,
            tuple(resolved_terms),
        )
        return context.prompt_text if context is not None else None

    return load


def _persist_conversation_turn(
    request: ChatRequest,
    result: ChatOrchestrationResult,
    session: AuthenticatedSession | None,
    session_id: str,
) -> None:
    """검색·확인 단계가 끝난 정상 대화 턴과 요약을 저장한다."""
    if session is None or not session_id:
        return
    blocked_statuses = {
        "CONFIRM",
        "AMBIGUOUS",
        "CONFIRMATION_EXPIRED",
        "CONFIRMATION_REJECTED",
    }
    if result.query_confirmation or result.resolution_status in blocked_statuses:
        return
    try:
        conversation_service.append_turn(
            session.access_token,
            session_id,
            result.original_question or request.question,
            result.answer,
            result.conversation_summary,
        )
    except SupabaseConversationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _should_persist_conversation_turn(
    result: ChatOrchestrationResult,
    session: AuthenticatedSession | None,
    session_id: str,
) -> bool:
    """현재 완료 결과가 실제 Supabase 저장 대상인지 확인한다.

    작성자: 김진우
    """
    blocked_statuses = {
        "CONFIRM",
        "AMBIGUOUS",
        "CONFIRMATION_EXPIRED",
        "CONFIRMATION_REJECTED",
    }
    return bool(
        session is not None
        and session_id
        and not result.query_confirmation
        and result.resolution_status not in blocked_statuses
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    session: AuthenticatedSession | None = Depends(optional_current_session),
) -> ChatResponse:
    """Safety Guard와 Intent 분류를 거쳐 선택된 챗봇 경로를 실행한다."""
    orchestrator = state.get("chat_orchestrator")
    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="챗봇 오케스트레이터가 준비되지 않았습니다.",
        )

    session_id, history, summary = _conversation_context(request, session)
    try:
        result = orchestrator.answer(
            request.question,
            history,
            summary,
            confirmation_id=request.confirmation_id,
            confirmation_answer=request.confirmation_answer,
            personal_context_loader=_personal_context_loader(session),
        )
    except IntentClassifierUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupabaseConversationError as exc:
        status_code = exc.status_code if exc.status_code in {400, 403, 404, 503} else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    _persist_conversation_turn(request, result, session, session_id)
    return _to_chat_response(request.question, result, session_id)


@router.post(
    "/chat/stream",
)
def stream_chat(
    request: ChatRequest,
    session: AuthenticatedSession | None = Depends(optional_current_session),
) -> StreamingResponse:
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
            yield _sse_event(
                "progress",
                {
                    "stage": "load_conversation",
                    "message": PROGRESS_MESSAGES["load_conversation"],
                },
            )
            session_id, history, summary = _conversation_context(request, session)
            for stream_event in orchestrator.stream_answer(
                request.question,
                history,
                summary,
                confirmation_id=request.confirmation_id,
                confirmation_answer=request.confirmation_answer,
                personal_context_loader=_personal_context_loader(session),
            ):
                if stream_event.event == "progress":
                    if stream_event.stage == "answer_stream_complete":
                        yield _sse_event(
                            "progress",
                            {"stage": stream_event.stage, "message": ""},
                        )
                        continue
                    message = PROGRESS_MESSAGES.get(stream_event.stage)
                    if message:
                        yield _sse_event(
                            "progress",
                            {"stage": stream_event.stage, "message": message},
                        )
                    continue
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
                    session_id,
                )
                if _should_persist_conversation_turn(
                    stream_event.result,
                    session,
                    session_id,
                ):
                    yield _sse_event(
                        "progress",
                        {
                            "stage": "save_conversation",
                            "message": PROGRESS_MESSAGES["save_conversation"],
                        },
                    )
                _persist_conversation_turn(
                    request,
                    stream_event.result,
                    session,
                    session_id,
                )
                yield _sse_event(
                    "complete",
                    response.model_dump(mode="json"),
                )
        except (IntentClassifierUnavailableError, SearchUnavailableError) as exc:
            yield _sse_event("error", {"message": str(exc)})
        except SupabaseConversationError as exc:
            yield _sse_event("error", {"message": str(exc)})
        except HTTPException as exc:
            yield _sse_event("error", {"message": str(exc.detail)})
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
