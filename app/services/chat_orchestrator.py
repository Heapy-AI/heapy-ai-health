"""최상위 Intent에 따라 챗봇 처리 경로를 실행하는 오케스트레이터.

작성자: 김진우
수정: 고수연 (멀티턴 추가)
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from langchain_core.documents import Document

from app.services.grounded_rag import (
    GroundedAnswerResult,
    GroundedRagService,
    NOT_GROUNDED_ANSWER,
)
from app.services.intent_classifier import (
    INTENT_LABELS,
    Intent,
    IntentPrediction,
    LinearIntentClassifier,
)
from app.services.conversation_summary import (
    ConversationSummarizer,
    SummaryUpdateResult,
    select_evicted_turns,
)
from app.services.query_rewriter import (
    QueryRewriteResult,
    QueryRewriter,
    normalize_history,
)
from app.services.safety_guard import GuardResult, check_safety_guard
from app.services.search_result_merger import merge_search_results
from app.services.vector_search import PineconeSearchService


GENERAL_IGNORE_ANSWER = "죄송합니다. 건강 관련 문의만 도와드릴 수 있어요."
SAFETY_IGNORE_ANSWER = (
    "안전상 질병의 확정 진단, 복약 결정 또는 내원 여부를 대신 판단할 수 없습니다. "
    "의료진이나 전문 의료기관에 상담해 주세요."
)


class IntentClassifierUnavailableError(RuntimeError):
    """Intent 모델이 준비되지 않아 오케스트레이션할 수 없는 경우."""


class SearchUnavailableError(RuntimeError):
    """모든 Pinecone namespace 검색이 실패한 경우."""


@dataclass(frozen=True)
class ChatOrchestrationResult:
    """단일 챗봇 요청의 분류·검색·답변 결과."""

    intent: Intent
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool
    model_version: str
    intent_source: str
    guard_triggered: bool
    guard_reason: str | None
    matched_patterns: list[str]
    answer: str
    grounded: bool | None
    documents: list[Document] = field(default_factory=list)
    cited_chunk_ids: list[str] = field(default_factory=list)
    verification_method: str = "not_applicable"
    verification_reason: str = "not_applicable"
    grounding_errors: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    grounding_plan: dict | None = None
    audit_status: str = "not_applicable"
    audit_summary: str = ""
    searched_collections: list[str] = field(default_factory=list)
    failed_collections: list[str] = field(default_factory=list)
    personal_context_used: bool = False
    original_question: str = ""
    search_question: str = ""
    query_rewritten: bool = False
    rewrite_reason: str = ""
    rewrite_error: str | None = None
    conversation_summary: str = ""
    summary_updated: bool = False
    summary_reason: str = ""


@dataclass(frozen=True)
class ChatStreamEvent:
    """스트리밍 토큰 또는 검증 완료 결과 이벤트.

    작성자: 김진우
    """

    event: str
    text: str = ""
    result: ChatOrchestrationResult | None = None


class ChatOrchestrator:
    """Safety Guard와 Intent 분류 결과에 맞는 MVP 응답 경로를 실행한다."""

    def __init__(
        self,
        *,
        vector_search: PineconeSearchService,
        intent_classifier: LinearIntentClassifier | None,
        grounded_rag_service: GroundedRagService,
        general_chat_chain,
        search_collections: tuple[str, ...],
        top_k_per_collection: int,
        final_top_k: int,
        max_per_collection: int,
        min_score: float,
        query_rewriter: QueryRewriter | None = None,
        conversation_summarizer: ConversationSummarizer | None = None,
    ) -> None:
        self._vector_search = vector_search
        self._intent_classifier = intent_classifier
        self._grounded_rag_service = grounded_rag_service
        self._general_chat_chain = general_chat_chain
        self._search_collections = search_collections
        self._top_k_per_collection = top_k_per_collection
        self._final_top_k = final_top_k
        self._max_per_collection = max_per_collection
        self._min_score = min_score
        self._query_rewriter = query_rewriter
        self._conversation_summarizer = conversation_summarizer

    def _prepare_question(
        self, question: str, history, summary: str = ""
    ) -> QueryRewriteResult:
        """직전 대화나 요약이 있으면 질문을 독립형으로 재작성한다."""
        if self._query_rewriter is None or not (history or summary):
            return QueryRewriteResult(
                question=question,
                original_question=question,
                rewritten=False,
                reason="멀티턴 재작성을 사용하지 않았습니다.",
            )
        return self._query_rewriter.rewrite(question, history, summary)

    def answer(
        self, question: str, history=(), summary: str = ""
    ) -> ChatOrchestrationResult:
        """질문에 답하고, 창 밖으로 밀려난 대화를 요약에 반영해 함께 돌려준다."""
        result = self._answer_core(question, history, summary)
        return self._with_summary(result, question, history, summary)

    def _answer_core(
        self, question: str, history, summary: str
    ) -> ChatOrchestrationResult:
        """Safety Guard·재작성·Intent 분기를 거쳐 응답을 만든다."""
        # 재작성이 위험 표현을 지우더라도 막을 수 있도록 원문을 먼저 검사한다.
        guard_result = check_safety_guard(question)
        if guard_result.triggered:
            return self._build_guard_response(guard_result, question, question)

        rewrite = self._prepare_question(question, history, summary)
        # 재작성으로 비로소 드러나는 위험 표현("그럼 저는 해당되나요?")을 잡는다.
        if rewrite.rewritten:
            rewritten_guard = check_safety_guard(rewrite.question)
            if rewritten_guard.triggered:
                return self._build_guard_response(
                    rewritten_guard, question, rewrite.question, rewrite
                )

        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._vector_search.embed_query(rewrite.question)
        prediction = self._intent_classifier.predict(query_embedding)

        if prediction.intent is Intent.IGNORE:
            return self._build_ignore_response(prediction, rewrite)
        if prediction.intent is Intent.GENERAL_CHAT:
            return self._build_general_chat_response(
                rewrite.question, prediction, rewrite
            )
        return self._build_rag_response(
            rewrite.question, query_embedding, prediction, rewrite
        )

    def stream_answer(
        self, question: str, history=(), summary: str = ""
    ) -> Iterator[ChatStreamEvent]:
        """토큰을 흘려보낸 뒤, 완료 이벤트에 갱신된 요약을 실어 보낸다.

        요약 갱신은 스트리밍이 끝난 뒤에 수행하므로 TTFB에 영향을 주지 않는다.
        """
        for event in self._stream_core(question, history, summary):
            if event.event != "complete" or event.result is None:
                yield event
                continue
            yield ChatStreamEvent(
                event="complete",
                result=self._with_summary(event.result, question, history, summary),
            )

    def _stream_core(
        self, question: str, history, summary: str
    ) -> Iterator[ChatStreamEvent]:
        """Intent 경로에 따라 LLM 토큰과 검증 완료 결과를 순서대로 전달한다.

        작성자: 김진우
        """
        guard_result = check_safety_guard(question)
        if guard_result.triggered:
            yield from self._stream_fixed_result(
                self._build_guard_response(guard_result, question, question)
            )
            return

        rewrite = self._prepare_question(question, history, summary)
        if rewrite.rewritten:
            rewritten_guard = check_safety_guard(rewrite.question)
            if rewritten_guard.triggered:
                yield from self._stream_fixed_result(
                    self._build_guard_response(
                        rewritten_guard, question, rewrite.question, rewrite
                    )
                )
                return

        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._vector_search.embed_query(rewrite.question)
        prediction = self._intent_classifier.predict(query_embedding)
        if prediction.intent is Intent.IGNORE:
            yield from self._stream_fixed_result(
                self._build_ignore_response(prediction, rewrite)
            )
            return
        if prediction.intent is Intent.GENERAL_CHAT:
            yield from self._stream_general_chat_response(
                rewrite.question, prediction, rewrite
            )
            return
        yield from self._stream_rag_response(
            rewrite.question,
            query_embedding,
            prediction,
            rewrite,
        )

    def _with_summary(
        self,
        result: ChatOrchestrationResult,
        question: str,
        history,
        summary: str,
    ) -> ChatOrchestrationResult:
        """이번 턴을 포함해 창 밖으로 밀려난 대화를 요약에 반영한다."""
        previous = (summary or "").strip()
        if self._conversation_summarizer is None:
            return replace(
                result,
                conversation_summary=previous,
                summary_updated=False,
                summary_reason="대화 요약을 사용하지 않습니다.",
            )

        turns = normalize_history(history)
        turns = turns + normalize_history(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": result.answer},
            ]
        )
        update: SummaryUpdateResult = self._conversation_summarizer.update(
            previous, select_evicted_turns(turns)
        )
        return replace(
            result,
            conversation_summary=update.summary,
            summary_updated=update.updated,
            summary_reason=update.reason,
        )

    @staticmethod
    def _rewrite_fields(
        rewrite: QueryRewriteResult | None,
        original_question: str = "",
        search_question: str = "",
    ) -> dict:
        """멀티턴 재작성 메타데이터를 응답에 싣는다."""
        if rewrite is None:
            return {
                "original_question": original_question,
                "search_question": search_question or original_question,
                "query_rewritten": False,
                "rewrite_reason": "",
                "rewrite_error": None,
            }
        return {
            "original_question": rewrite.original_question,
            "search_question": rewrite.question,
            "query_rewritten": rewrite.rewritten,
            "rewrite_reason": rewrite.reason,
            "rewrite_error": rewrite.error,
        }

    def _build_guard_response(
        self,
        guard_result: GuardResult,
        original_question: str = "",
        search_question: str = "",
        rewrite: QueryRewriteResult | None = None,
    ) -> ChatOrchestrationResult:
        probabilities = {label: 0.0 for label in INTENT_LABELS}
        probabilities[Intent.IGNORE.value] = 1.0
        return ChatOrchestrationResult(
            intent=Intent.IGNORE,
            confidence=1.0,
            probabilities=probabilities,
            uncertain=False,
            model_version=(
                self._intent_classifier.model_version
                if self._intent_classifier is not None
                else "unavailable"
            ),
            intent_source="safety_guard",
            guard_triggered=True,
            guard_reason=guard_result.reason,
            matched_patterns=guard_result.matched_patterns,
            answer=SAFETY_IGNORE_ANSWER,
            grounded=None,
            verification_method="fixed_response",
            verification_reason=f"safety_guard:{guard_result.reason}",
            **self._rewrite_fields(rewrite, original_question, search_question),
        )

    @staticmethod
    def _prediction_fields(prediction: IntentPrediction) -> dict:
        return {
            "intent": prediction.intent,
            "confidence": prediction.confidence,
            "probabilities": prediction.probabilities,
            "uncertain": prediction.uncertain,
            "model_version": prediction.model_version,
            "intent_source": "linear_classifier",
            "guard_triggered": False,
            "guard_reason": None,
            "matched_patterns": [],
        }

    def _build_ignore_response(
        self,
        prediction: IntentPrediction,
        rewrite: QueryRewriteResult | None = None,
    ) -> ChatOrchestrationResult:
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction),
            **self._rewrite_fields(rewrite),
            answer=GENERAL_IGNORE_ANSWER,
            grounded=None,
            verification_method="fixed_response",
            verification_reason="intent:ignore",
        )

    def _build_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
        rewrite: QueryRewriteResult | None = None,
    ) -> ChatOrchestrationResult:
        answer = str(self._general_chat_chain.invoke({"question": question})).strip()
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction),
            **self._rewrite_fields(rewrite, question, question),
            answer=answer,
            grounded=None,
            verification_method="not_applicable",
            verification_reason="intent:general_chat",
        )

    def _stream_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
        rewrite: QueryRewriteResult | None = None,
    ) -> Iterator[ChatStreamEvent]:
        """검색 없는 일반 대화의 Gemini 토큰을 전달한다.

        작성자: 김진우
        """
        answer_parts: list[str] = []
        for token in self._general_chat_chain.stream({"question": question}):
            text = str(token)
            if not text:
                continue
            answer_parts.append(text)
            yield ChatStreamEvent(event="token", text=text)

        result = ChatOrchestrationResult(
            **self._prediction_fields(prediction),
            **self._rewrite_fields(rewrite, question, question),
            answer="".join(answer_parts).strip(),
            grounded=None,
            verification_method="not_applicable",
            verification_reason="intent:general_chat",
        )
        yield ChatStreamEvent(event="complete", result=result)

    def _build_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
        rewrite: QueryRewriteResult | None = None,
    ) -> ChatOrchestrationResult:
        documents, searched_collections, failed_collections = (
            self._search_rag_documents(query_embedding)
        )
        verification_reason = (
            "intent_uncertain"
            if prediction.uncertain
            else f"intent:{prediction.intent.value}"
        )
        if not documents:
            return ChatOrchestrationResult(
                **self._prediction_fields(prediction),
                **self._rewrite_fields(rewrite, question, question),
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                verification_method="plan_rejected",
                verification_reason="no_search_results",
                grounding_errors=["검색된 최종 청크가 없습니다."],
                audit_status="not_run",
                audit_summary="근거 계획을 생성하지 않았습니다.",
                searched_collections=searched_collections,
                failed_collections=failed_collections,
            )

        verify_semantics = (
            prediction.intent is Intent.COMPREHENSIVE or prediction.uncertain
        )
        grounded_result: GroundedAnswerResult = self._grounded_rag_service.answer(
            question,
            documents,
            verify_semantics=verify_semantics,
        )
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction),
            **self._rewrite_fields(rewrite, question, question),
            answer=grounded_result.answer,
            grounded=grounded_result.grounded,
            documents=documents,
            cited_chunk_ids=grounded_result.cited_chunk_ids,
            verification_method=grounded_result.verification_method,
            verification_reason=verification_reason,
            grounding_errors=grounded_result.grounding_errors,
            unsupported_claims=grounded_result.unsupported_claims,
            grounding_plan=(
                grounded_result.grounding_plan.model_dump(mode="json")
                if grounded_result.grounding_plan is not None
                else None
            ),
            audit_status=grounded_result.audit_status,
            audit_summary=grounded_result.audit_summary,
            searched_collections=searched_collections,
            failed_collections=failed_collections,
            personal_context_used=False,
        )

    def _stream_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
        rewrite: QueryRewriteResult | None = None,
    ) -> Iterator[ChatStreamEvent]:
        """근거 계획 승인 후 최종 답변을 스트리밍하고 감사 결과를 반환한다.

        작성자: 김진우
        """
        documents, searched_collections, failed_collections = (
            self._search_rag_documents(query_embedding)
        )
        if not documents:
            result = ChatOrchestrationResult(
                **self._prediction_fields(prediction),
                **self._rewrite_fields(rewrite, question, question),
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                verification_method="plan_rejected",
                verification_reason="no_search_results",
                grounding_errors=["검색된 최종 청크가 없습니다."],
                audit_status="not_run",
                audit_summary="근거 계획을 생성하지 않았습니다.",
                searched_collections=searched_collections,
                failed_collections=failed_collections,
            )
            yield from self._stream_fixed_result(result)
            return

        verify_semantics = (
            prediction.intent is Intent.COMPREHENSIVE or prediction.uncertain
        )
        verification_reason = (
            "intent_uncertain"
            if prediction.uncertain
            else f"intent:{prediction.intent.value}"
        )
        for event in self._grounded_rag_service.stream_answer(
            question,
            documents,
            verify_semantics=verify_semantics,
        ):
            if isinstance(event, str):
                yield ChatStreamEvent(event="token", text=event)
                continue
            result = ChatOrchestrationResult(
                **self._prediction_fields(prediction),
                **self._rewrite_fields(rewrite, question, question),
                answer=event.answer,
                grounded=event.grounded,
                documents=documents,
                cited_chunk_ids=event.cited_chunk_ids,
                verification_method=event.verification_method,
                verification_reason=verification_reason,
                grounding_errors=event.grounding_errors,
                unsupported_claims=event.unsupported_claims,
                grounding_plan=(
                    event.grounding_plan.model_dump(mode="json")
                    if event.grounding_plan is not None
                    else None
                ),
                audit_status=event.audit_status,
                audit_summary=event.audit_summary,
                searched_collections=searched_collections,
                failed_collections=failed_collections,
                personal_context_used=False,
            )
            yield ChatStreamEvent(event="complete", result=result)

    def _search_rag_documents(
        self,
        query_embedding: list[float],
    ) -> tuple[list[Document], list[str], list[str]]:
        """설정된 namespace를 검색하고 최종 문맥 청크를 병합한다.

        작성자: 김진우
        """
        search_result = self._vector_search.search_many_by_vector(
            self._search_collections,
            query_embedding,
            self._top_k_per_collection,
        )
        if (
            search_result.errors
            and len(search_result.errors) == len(search_result.searched_collections)
        ):
            raise SearchUnavailableError("모든 Pinecone namespace 검색에 실패했습니다.")

        documents = merge_search_results(
            search_result.documents,
            final_top_k=self._final_top_k,
            max_per_collection=self._max_per_collection,
            min_score=self._min_score,
        )
        return (
            documents,
            search_result.searched_collections,
            sorted(search_result.errors),
        )

    @staticmethod
    def _stream_fixed_result(
        result: ChatOrchestrationResult,
    ) -> Iterator[ChatStreamEvent]:
        """LLM을 사용하지 않는 확정 응답을 동일한 이벤트 계약으로 전달한다.

        작성자: 김진우
        """
        yield ChatStreamEvent(event="token", text=result.answer)
        yield ChatStreamEvent(event="complete", result=result)
