"""최상위 Intent에 따라 챗봇 처리 경로를 실행하는 오케스트레이터.

작성자: 김진우
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
    searched_collections: list[str] = field(default_factory=list)
    failed_collections: list[str] = field(default_factory=list)
    personal_context_used: bool = False


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
        guard_result = check_safety_guard(question)
        if guard_result.triggered:
            return self._build_guard_response(guard_result)

        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._vector_search.embed_query(question)
        prediction = self._intent_classifier.predict(query_embedding)

        if prediction.intent is Intent.IGNORE:
            return self._build_ignore_response(prediction)
        if prediction.intent is Intent.GENERAL_CHAT:
            return self._build_general_chat_response(question, prediction)
        return self._build_rag_response(question, query_embedding, prediction)

    def _build_guard_response(
        self,
        guard_result: GuardResult,
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
    ) -> ChatOrchestrationResult:
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction),
            answer=GENERAL_IGNORE_ANSWER,
            grounded=None,
            verification_method="fixed_response",
            verification_reason="intent:ignore",
        )

    def _build_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
    ) -> ChatOrchestrationResult:
        answer = str(self._general_chat_chain.invoke({"question": question})).strip()
        return ChatOrchestrationResult(
            **self._prediction_fields(prediction),
            answer=answer,
            grounded=None,
            verification_method="not_applicable",
            verification_reason="intent:general_chat",
        )

    def _build_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
    ) -> ChatOrchestrationResult:
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
        failed_collections = sorted(search_result.errors)
        verification_reason = (
            "intent_uncertain"
            if prediction.uncertain
            else f"intent:{prediction.intent.value}"
        )
        if not documents:
            return ChatOrchestrationResult(
                **self._prediction_fields(prediction),
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                verification_method="citation_validation_failed",
                verification_reason="no_search_results",
                grounding_errors=["검색된 최종 청크가 없습니다."],
                searched_collections=search_result.searched_collections,
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
            answer=grounded_result.answer,
            grounded=grounded_result.grounded,
            documents=documents,
            cited_chunk_ids=grounded_result.cited_chunk_ids,
            verification_method=grounded_result.verification_method,
            verification_reason=verification_reason,
            grounding_errors=grounded_result.grounding_errors,
            unsupported_claims=grounded_result.unsupported_claims,
            searched_collections=search_result.searched_collections,
            failed_collections=failed_collections,
            personal_context_used=False,
        )
