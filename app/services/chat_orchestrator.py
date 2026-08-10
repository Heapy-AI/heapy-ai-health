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
from app.services.query_resolver import (
    QueryResolution,
    build_confirmed_query_resolution,
)
from app.services.vector_search import PineconeSearchService


GENERAL_IGNORE_ANSWER = "죄송합니다. 건강 관련 문의만 도와드릴 수 있어요."
SAFETY_IGNORE_ANSWER = (
    "안전상 질병의 확정 진단, 복약 결정 또는 내원 여부를 대신 판단할 수 없습니다. "
    "의료진이나 전문 의료기관에 상담해 주세요."
)
MEDICAL_ADVICE_ANSWER = (
    "통증이나 증상의 원인은 다양해서 증상만으로 특정 약을 추천할 수 없습니다. "
    "기저질환, 알레르기, 복용 중인 약·영양제에 따라 약이 오히려 부담이 될 수 있으니 "
    "임의로 복용하거나 용량을 늘리지 말고 의료진 또는 약사와 확인해 주세요.\n\n"
    "피부나 눈이 노래짐, 심하거나 점점 심해지는 통증, 고열, 반복되는 구토, "
    "배가 갑자기 붓는 증상, 의식이 흐려짐, 피를 토하거나 검은변이 있으면 "
    "즉시 응급진료를 받으세요."
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
    resolved_query: str = ""
    resolved_terms: list[dict] = field(default_factory=list)
    query_confirmation: bool = False
    confirmation_question: str = ""
    confirmation_id: str = ""
    resolution_status: str = "NO_MATCH"


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

    def answer(
        self,
        question: str,
        *,
        confirmed_term: dict | None = None,
    ) -> ChatOrchestrationResult:
        """질문을 한 번 분류하고 선택된 Intent 경로의 최종 응답을 반환한다."""
        query_resolution = self._resolve_query(
            question,
            confirmed_term=confirmed_term,
        )
        guard_result = check_safety_guard(question, resolution=query_resolution)
        if guard_result.triggered:
            return self._build_guard_response(guard_result, query_resolution)

        if query_resolution.needs_confirmation:
            return self._build_query_confirmation_response(query_resolution)
        if query_resolution.resolution_status == "AMBIGUOUS":
            return self._build_query_ambiguous_response(query_resolution)

        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._embed_resolved_query(query_resolution)
        prediction = self._intent_classifier.predict(query_embedding)

        if prediction.intent is Intent.IGNORE:
            return self._build_ignore_response(prediction)
        if prediction.intent is Intent.GENERAL_CHAT:
            return self._build_general_chat_response(question, prediction)
        return self._build_rag_response(
            question,
            query_embedding,
            prediction,
            query_resolution,
        )

    def stream_answer(
        self,
        question: str,
        *,
        confirmed_term: dict | None = None,
    ) -> Iterator[ChatStreamEvent]:
        """Intent 경로에 따라 LLM 토큰과 검증 완료 결과를 순서대로 전달한다.

        작성자: 김진우
        """
        query_resolution = self._resolve_query(
            question,
            confirmed_term=confirmed_term,
        )
        guard_result = check_safety_guard(question, resolution=query_resolution)
        if guard_result.triggered:
            yield from self._stream_fixed_result(
                self._build_guard_response(guard_result, query_resolution)
            )
            return

        if query_resolution.needs_confirmation:
            yield from self._stream_fixed_result(
                self._build_query_confirmation_response(query_resolution)
            )
            return
        if query_resolution.resolution_status == "AMBIGUOUS":
            yield from self._stream_fixed_result(
                self._build_query_ambiguous_response(query_resolution)
            )
            return

        if self._intent_classifier is None:
            raise IntentClassifierUnavailableError(
                "학습된 intent 모델이 없어 챗봇 경로를 선택할 수 없습니다."
            )

        query_embedding = self._embed_resolved_query(query_resolution)
        prediction = self._intent_classifier.predict(query_embedding)
        if prediction.intent is Intent.IGNORE:
            yield from self._stream_fixed_result(
                self._build_ignore_response(prediction)
            )
            return
        if prediction.intent is Intent.GENERAL_CHAT:
            yield from self._stream_general_chat_response(question, prediction)
            return
        yield from self._stream_rag_response(
            question,
            query_embedding,
            prediction,
            query_resolution,
        )

    def _resolve_query(
        self,
        question: str,
        *,
        confirmed_term: dict | None = None,
    ) -> QueryResolution:
        if confirmed_term is not None:
            return build_confirmed_query_resolution(question, confirmed_term)
        resolver = getattr(self._vector_search, "resolve_query", None)
        if callable(resolver):
            return resolver(question)
        return QueryResolution(question, question)

    def _embed_resolved_query(self, resolution: QueryResolution) -> list[float]:
        set_resolution = getattr(self._vector_search, "set_query_resolution", None)
        if callable(set_resolution):
            set_resolution(resolution)
        embed_resolved = getattr(self._vector_search, "embed_resolved_query", None)
        if callable(embed_resolved):
            return embed_resolved(resolution.resolved_query)
        # 기존 검색 서비스 대체 구현과 테스트 fake도 계속 지원한다.
        return self._vector_search.embed_query(resolution.resolved_query)

    def _build_guard_response(
        self,
        guard_result: GuardResult,
        query_resolution: QueryResolution | None = None,
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
            answer=(
                MEDICAL_ADVICE_ANSWER
                if guard_result.reason == "symptom_medication_advice"
                else SAFETY_IGNORE_ANSWER
            ),
            grounded=None,
            verification_method="fixed_response",
            verification_reason=f"safety_guard:{guard_result.reason}",
            resolved_query=(
                query_resolution.resolved_query if query_resolution is not None else ""
            ),
            resolved_terms=(
                [term.as_dict() for term in query_resolution.terms]
                if query_resolution is not None
                else []
            ),
            resolution_status=(
                query_resolution.resolution_status
                if query_resolution is not None
                else "NO_MATCH"
            ),
        )

    def _build_query_confirmation_response(
        self,
        query_resolution: QueryResolution,
    ) -> ChatOrchestrationResult:
        probabilities = {label: 0.0 for label in INTENT_LABELS}
        probabilities[Intent.SIMPLE_LOOKUP.value] = 1.0
        return ChatOrchestrationResult(
            intent=Intent.SIMPLE_LOOKUP,
            confidence=1.0,
            probabilities=probabilities,
            uncertain=False,
            model_version=(
                self._intent_classifier.model_version
                if self._intent_classifier is not None
                else "query-resolver"
            ),
            intent_source="query_resolver",
            guard_triggered=False,
            guard_reason=None,
            matched_patterns=[],
            answer=query_resolution.confirmation_question,
            grounded=None,
            verification_method="query_confirmation",
            verification_reason="query_resolver:confirmation_required",
            audit_status="not_applicable",
            audit_summary="오인식 가능성이 있는 표준용어 후보를 확인한 뒤 검색을 보류했습니다.",
            resolved_query=query_resolution.resolved_query,
            resolved_terms=[term.as_dict() for term in query_resolution.terms],
            query_confirmation=True,
            confirmation_question=query_resolution.confirmation_question,
            resolution_status=query_resolution.resolution_status,
        )

    def _build_query_ambiguous_response(
        self,
        query_resolution: QueryResolution,
    ) -> ChatOrchestrationResult:
        """여러 표준용어로 해석되는 입력을 강제 검색하지 않는다."""
        probabilities = {label: 0.0 for label in INTENT_LABELS}
        probabilities[Intent.SIMPLE_LOOKUP.value] = 1.0
        answer = (
            "입력하신 검색어가 여러 건강정보 항목으로 해석될 수 있어요. "
            "질환명이나 검사명을 조금 더 정확하게 입력해 주세요."
        )
        return ChatOrchestrationResult(
            intent=Intent.SIMPLE_LOOKUP,
            confidence=1.0,
            probabilities=probabilities,
            uncertain=False,
            model_version=(
                self._intent_classifier.model_version
                if self._intent_classifier is not None
                else "query-resolver"
            ),
            intent_source="query_resolver",
            guard_triggered=False,
            guard_reason=None,
            matched_patterns=[],
            answer=answer,
            grounded=None,
            verification_method="query_ambiguity",
            verification_reason="query_resolver:ambiguous_candidates",
            audit_status="not_applicable",
            audit_summary="모호한 표준용어 후보가 있어 검색을 보류했습니다.",
            resolved_query=query_resolution.resolved_query,
            resolved_terms=[term.as_dict() for term in query_resolution.terms],
            resolution_status=query_resolution.resolution_status,
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

    def _stream_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
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
        query_resolution: QueryResolution,
    ) -> ChatOrchestrationResult:
        documents, searched_collections, failed_collections = (
            self._search_rag_documents(query_embedding, query_resolution)
        )
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
                verification_method="plan_rejected",
                verification_reason="no_search_results",
                grounding_errors=["검색된 최종 청크가 없습니다."],
                audit_status="not_run",
                audit_summary="근거 계획을 생성하지 않았습니다.",
                searched_collections=searched_collections,
                failed_collections=failed_collections,
                resolved_query=query_resolution.resolved_query,
                resolved_terms=[term.as_dict() for term in query_resolution.terms],
                resolution_status=query_resolution.resolution_status,
            )

        verify_semantics = (
            prediction.intent is Intent.COMPREHENSIVE or prediction.uncertain
        )
        grounded_result: GroundedAnswerResult = self._grounded_rag_service.answer(
            query_resolution.resolved_query,
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
            resolved_query=query_resolution.resolved_query,
            resolved_terms=[term.as_dict() for term in query_resolution.terms],
            resolution_status=query_resolution.resolution_status,
        )

    def _stream_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
        query_resolution: QueryResolution,
    ) -> Iterator[ChatStreamEvent]:
        """근거 계획 승인 후 최종 답변을 스트리밍하고 감사 결과를 반환한다.

        작성자: 김진우
        """
        documents, searched_collections, failed_collections = (
            self._search_rag_documents(query_embedding, query_resolution)
        )
        if not documents:
            result = ChatOrchestrationResult(
                **self._prediction_fields(prediction),
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                verification_method="plan_rejected",
                verification_reason="no_search_results",
                grounding_errors=["검색된 최종 청크가 없습니다."],
                audit_status="not_run",
                audit_summary="근거 계획을 생성하지 않았습니다.",
                searched_collections=searched_collections,
                failed_collections=failed_collections,
                resolved_query=query_resolution.resolved_query,
                resolved_terms=[term.as_dict() for term in query_resolution.terms],
                resolution_status=query_resolution.resolution_status,
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
            query_resolution.resolved_query,
            documents,
            verify_semantics=verify_semantics,
        ):
            if isinstance(event, str):
                yield ChatStreamEvent(event="token", text=event)
                continue
            result = ChatOrchestrationResult(
                **self._prediction_fields(prediction),
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
                resolved_query=query_resolution.resolved_query,
                resolved_terms=[term.as_dict() for term in query_resolution.terms],
                resolution_status=query_resolution.resolution_status,
            )
            yield ChatStreamEvent(event="complete", result=result)

    def _search_rag_documents(
        self,
        query_embedding: list[float],
        query_resolution: QueryResolution | None = None,
    ) -> tuple[list[Document], list[str], list[str]]:
        """설정된 namespace를 검색하고 최종 문맥 청크를 병합한다.

        작성자: 김진우
        """
        collections = self._collections_for_resolution(query_resolution)
        search_result = self._vector_search.search_many_by_vector(
            collections,
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

    def _collections_for_resolution(
        self,
        query_resolution: QueryResolution | None,
    ) -> tuple[str, ...]:
        """RDB 용어 타입·복합어 힌트에 맞는 namespace를 우선 검색한다."""
        if query_resolution is None or query_resolution.domain_hint != "MEDICATION":
            return self._search_collections

        medication_collections = tuple(
            collection
            for collection in self._search_collections
            if "medication" in collection.casefold()
        )
        return medication_collections or self._search_collections

    @staticmethod
    def _stream_fixed_result(
        result: ChatOrchestrationResult,
    ) -> Iterator[ChatStreamEvent]:
        """LLM을 사용하지 않는 확정 응답을 동일한 이벤트 계약으로 전달한다.

        작성자: 김진우
        """
        yield ChatStreamEvent(event="token", text=result.answer)
        yield ChatStreamEvent(event="complete", result=result)
