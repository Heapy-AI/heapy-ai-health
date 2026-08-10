"""최상위 Intent에 따라 챗봇 처리 경로를 실행하는 오케스트레이터.

작성자: 김진우
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_core.documents import Document

from app.services.grounded_rag import (
    GroundedAnswerResult,
    GroundedRagService,
)
from app.services.intent_classifier import (
    Intent,
    IntentPrediction,
    LinearIntentClassifier,
)
from app.services.safety_guard import GuardResult, RiskLevel, check_safety_guard
from app.services.search_result_merger import merge_search_results
from app.services.vector_search import PineconeSearchService


GENERAL_IGNORE_ANSWER = "죄송합니다. 건강 관련 문의만 도와드릴 수 있어요."


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
    risk_level: str
    restricted_actions: list[str]
    response_policy: str
    emergency: bool
    answer: str
    grounded: bool | None
    documents: list[Document] = field(default_factory=list)
    cited_chunk_ids: list[str] = field(default_factory=list)
    verification_method: str = "not_applicable"
    verification_reason: str = "not_applicable"
    grounding_errors: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    evidence_status: str = "not_applicable"
    retrieval_assessment: dict | None = None
    audit_status: str = "not_applicable"
    audit_summary: str = ""
    unanswered_items: list[str] = field(default_factory=list)
    safety_violations: list[str] = field(default_factory=list)
    searched_collections: list[str] = field(default_factory=list)
    failed_collections: list[str] = field(default_factory=list)
    personal_context_used: bool = False


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

    def answer(self, question: str) -> ChatOrchestrationResult:
        """질문을 한 번 분류하고 선택된 Intent 경로의 최종 응답을 반환한다."""
        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._vector_search.embed_query(question)
        prediction = self._intent_classifier.predict(query_embedding)
        guard_result = check_safety_guard(question)

        if prediction.intent is Intent.IGNORE:
            return self._build_ignore_response(prediction, guard_result)
        if prediction.intent is Intent.GENERAL_CHAT:
            return self._build_general_chat_response(question, prediction, guard_result)
        return self._build_rag_response(
            question,
            query_embedding,
            prediction,
            guard_result,
        )

    def stream_answer(self, question: str) -> Iterator[ChatStreamEvent]:
        """Intent 경로에 따라 LLM 토큰과 검증 완료 결과를 순서대로 전달한다.

        작성자: 김진우
        """
        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._vector_search.embed_query(question)
        prediction = self._intent_classifier.predict(query_embedding)
        guard_result = check_safety_guard(question)
        if prediction.intent is Intent.IGNORE:
            yield from self._stream_fixed_result(
                self._build_ignore_response(prediction, guard_result)
            )
            return
        if prediction.intent is Intent.GENERAL_CHAT:
            yield from self._stream_general_chat_response(
                question,
                prediction,
                guard_result,
            )
            return
        yield from self._stream_rag_response(
            question,
            query_embedding,
            prediction,
            guard_result,
        )

    @staticmethod
    def _prediction_fields(
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> dict:
        return {
            "intent": prediction.intent,
            "confidence": prediction.confidence,
            "probabilities": prediction.probabilities,
            "uncertain": prediction.uncertain,
            "model_version": prediction.model_version,
            "intent_source": "linear_classifier",
            "guard_triggered": guard_result.triggered,
            "guard_reason": guard_result.reason,
            "matched_patterns": guard_result.matched_patterns,
            "risk_level": guard_result.risk_level.value,
            "restricted_actions": guard_result.restricted_actions,
            "response_policy": guard_result.response_policy,
            "emergency": guard_result.emergency,
        }

    def _build_ignore_response(
        self,
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> ChatOrchestrationResult:
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction, guard_result),
            answer=GENERAL_IGNORE_ANSWER,
            grounded=None,
            verification_method="fixed_response",
            verification_reason="intent:ignore",
        )

    def _build_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> ChatOrchestrationResult:
        answer = str(self._general_chat_chain.invoke({"question": question})).strip()
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction, guard_result),
            answer=answer,
            grounded=None,
            verification_method="not_applicable",
            verification_reason="intent:general_chat",
        )

    def _stream_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
        guard_result: GuardResult,
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
            **self._prediction_fields(prediction, guard_result),
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
        guard_result: GuardResult,
    ) -> ChatOrchestrationResult:
        documents, searched_collections, failed_collections = (
            self._search_rag_documents(query_embedding)
        )
        verification_reason = self._verification_reason(prediction, guard_result)
        grounded_result: GroundedAnswerResult = self._grounded_rag_service.answer(
            question,
            documents,
            safety_policy=guard_result,
        )
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction, guard_result),
            answer=grounded_result.answer,
            grounded=grounded_result.grounded,
            documents=documents,
            cited_chunk_ids=grounded_result.cited_chunk_ids,
            verification_method=grounded_result.verification_method,
            verification_reason=verification_reason,
            grounding_errors=grounded_result.grounding_errors,
            unsupported_claims=grounded_result.unsupported_claims,
            evidence_status=grounded_result.evidence_status,
            retrieval_assessment=grounded_result.retrieval_assessment.__dict__,
            audit_status=grounded_result.audit_status,
            audit_summary=grounded_result.audit_summary,
            unanswered_items=grounded_result.unanswered_items or [],
            safety_violations=grounded_result.safety_violations or [],
            searched_collections=searched_collections,
            failed_collections=failed_collections,
            personal_context_used=False,
        )

    def _stream_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> Iterator[ChatStreamEvent]:
        """검색 기본 검사 후 최종 답변을 스트리밍하고 감사 결과를 반환한다.

        작성자: 김진우
        """
        documents, searched_collections, failed_collections = (
            self._search_rag_documents(query_embedding)
        )
        verification_reason = self._verification_reason(prediction, guard_result)
        for event in self._grounded_rag_service.stream_answer(
            question,
            documents,
            safety_policy=guard_result,
        ):
            if isinstance(event, str):
                yield ChatStreamEvent(event="token", text=event)
                continue
            result = ChatOrchestrationResult(
                **self._prediction_fields(prediction, guard_result),
                answer=event.answer,
                grounded=event.grounded,
                documents=documents,
                cited_chunk_ids=event.cited_chunk_ids,
                verification_method=event.verification_method,
                verification_reason=verification_reason,
                grounding_errors=event.grounding_errors,
                unsupported_claims=event.unsupported_claims,
                evidence_status=event.evidence_status,
                retrieval_assessment=event.retrieval_assessment.__dict__,
                audit_status=event.audit_status,
                audit_summary=event.audit_summary,
                unanswered_items=event.unanswered_items or [],
                safety_violations=event.safety_violations or [],
                searched_collections=searched_collections,
                failed_collections=failed_collections,
                personal_context_used=False,
            )
            yield ChatStreamEvent(event="complete", result=result)

    @staticmethod
    def _verification_reason(
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> str:
        """Intent와 안전 정책을 모니터링용 한 줄 근거로 기록한다."""
        intent_reason = (
            "intent_uncertain"
            if prediction.uncertain
            else f"intent:{prediction.intent.value}"
        )
        if guard_result.risk_level is RiskLevel.NORMAL:
            return intent_reason
        return f"{intent_reason}|risk:{guard_result.risk_level.value}"

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
