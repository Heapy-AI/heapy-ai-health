"""최상위 Intent에 따라 챗봇 처리 경로를 실행하는 오케스트레이터.

작성자: 김진우
"""

from __future__ import annotations

import re

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace

from langchain_core.documents import Document

from app.services.chatbot_persona import (
    get_chatbot_persona_instruction,
)

from app.services.grounded_rag import (
    GroundedAnswerResult,
    GroundedRagProgress,
    GroundedRagService,
)

from app.services.intent_classifier import (
    Intent,
    IntentPrediction,
    LinearIntentClassifier,
)

from app.services.conversation_summary import (
    ConversationSummarizer,
    select_evicted_turns,
)

from app.services.query_confirmation import (
    QueryConfirmationStore,
)

from app.services.query_resolver import (
    MedicalQueryResolver,
    QueryResolution,
    build_confirmed_query_resolution,
)

from app.services.query_rewriter import (
    QueryRewriteResult,
    QueryRewriter,
    format_history,
    normalize_history,
)

from app.services.safety_guard import (
    GuardResult,
    RiskLevel,
    check_safety_guard,
)

from app.services.search_result_merger import (
    merge_search_results,
)

from app.services.vector_search import (
    PineconeSearchService,
)


GENERAL_IGNORE_ANSWER = (
    "죄송합니다. 건강 관련 문의만 도와드릴 수 있어요."
)


PERSONAL_HEALTH_QUESTION_PATTERN = re.compile(
    r"(?:^|\s)(?:내|나의|제|저의|내가|제가|나는|저는)(?:\s|$)"
)


class IntentClassifierUnavailableError(
    RuntimeError
):
    """Intent 모델이 준비되지 않은 경우."""


class SearchUnavailableError(
    RuntimeError
):
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

    documents: list[Document] = field(
        default_factory=list
    )

    cited_chunk_ids: list[str] = field(
        default_factory=list
    )

    verification_method: str = (
        "not_applicable"
    )

    verification_reason: str = (
        "not_applicable"
    )

    grounding_errors: list[str] = field(
        default_factory=list
    )

    unsupported_claims: list[str] = field(
        default_factory=list
    )

    evidence_status: str = (
        "not_applicable"
    )

    retrieval_assessment: dict | None = None

    audit_status: str = "not_applicable"

    audit_summary: str = ""

    unanswered_items: list[str] = field(
        default_factory=list
    )

    safety_violations: list[str] = field(
        default_factory=list
    )

    searched_collections: list[str] = field(
        default_factory=list
    )

    failed_collections: list[str] = field(
        default_factory=list
    )

    personal_context_used: bool = False

    original_question: str = ""

    standalone_question: str = ""

    resolved_query: str = ""

    query_rewritten: bool = False

    rewrite_reason: str = ""

    rewrite_error: str | None = None

    is_follow_up: bool = False

    current_topic: str = ""

    inherited_target: str = ""

    personal_context_required: bool = False

    resolved_terms: list[dict] = field(
        default_factory=list
    )

    resolution_status: str = "NO_MATCH"

    resolution_error: str | None = None

    query_confirmation: bool = False

    confirmation_question: str = ""

    confirmation_id: str = ""

    conversation_summary: str = ""

    summary_updated: bool = False

    summary_reason: str = ""


@dataclass(frozen=True)
class PreparedQuery:
    """멀티턴 재작성과 의료용어 정규화를 마친 요청 상태."""

    original_question: str

    standalone_question: str

    resolved_query: str

    query_rewritten: bool = False

    rewrite_reason: str = ""

    rewrite_error: str | None = None

    is_follow_up: bool = False

    current_topic: str = ""

    inherited_target: str = ""

    personal_context_required: bool = False

    context_analysis_performed: bool = False

    resolved_terms: list[dict] = field(
        default_factory=list
    )

    resolution_status: str = "NO_MATCH"

    resolution_error: str | None = None

    query_confirmation: bool = False

    confirmation_question: str = ""

    confirmation_id: str = ""

    blocked_answer: str = ""


@dataclass(frozen=True)
class ChatStreamEvent:
    """스트리밍 토큰 또는 검증 완료 결과 이벤트."""

    event: str

    text: str = ""

    stage: str = ""

    result: ChatOrchestrationResult | None = None


class ChatOrchestrator:
    """Safety Guard와 Intent 분류 결과에 맞는 응답 경로를 실행한다."""

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
        query_resolver: MedicalQueryResolver | None = None,
        conversation_summarizer: ConversationSummarizer | None = None,
        confirmation_store: QueryConfirmationStore | None = None,
    ) -> None:

        self._vector_search = vector_search

        self._intent_classifier = (
            intent_classifier
        )

        self._grounded_rag_service = (
            grounded_rag_service
        )

        self._general_chat_chain = (
            general_chat_chain
        )

        self._search_collections = (
            search_collections
        )

        self._top_k_per_collection = (
            top_k_per_collection
        )

        self._final_top_k = final_top_k

        self._max_per_collection = (
            max_per_collection
        )

        self._min_score = min_score

        self._query_rewriter = query_rewriter

        self._query_resolver = query_resolver

        self._conversation_summarizer = (
            conversation_summarizer
        )

        self._confirmation_store = (
            confirmation_store
        )

    def answer(
        self,
        question: str,
        history=(),
        summary: str = "",
        *,
        persona: str = "coach",
        confirmation_id: str = "",
        confirmation_answer: bool | None = None,
        personal_context_loader: Callable[
            [str, list[dict]],
            str | None,
        ] | None = None,
    ) -> ChatOrchestrationResult:

        persona_instruction = (
            get_chatbot_persona_instruction(
                persona
            )
        )

        prepared = self._prepare_query(
            question,
            history,
            summary,
            confirmation_id=confirmation_id,
            confirmation_answer=confirmation_answer,
        )

        conversation_context = (
            self._format_recent_context(
                history
            )
        )

        guard_result = (
            self._combined_guard(
                question,
                prepared.resolved_query,
            )
        )

        if prepared.blocked_answer:

            result = (
                self._build_query_blocked_response(
                    prepared,
                    guard_result,
                )
            )

            return self._with_summary(
                result,
                question,
                history,
                summary,
            )

        if self._intent_classifier is None:
            raise (
                IntentClassifierUnavailableError(
                    "학습된 intent 모델이 없어 "
                    "챗봇 경로를 선택할 수 없습니다."
                )
            )

        query_embedding = (
            self._vector_search.embed_query(
                prepared.resolved_query
            )
        )

        prediction = (
            self._intent_classifier.predict(
                query_embedding
            )
        )

        personal_context = None

        if self._should_load_personal_context(
            prepared,
            prediction,
            personal_context_loader,
            history,
            summary,
        ):

            personal_context = (
                personal_context_loader(
                    prepared.standalone_question,
                    prepared.resolved_terms,
                )
            )

            prediction = (
                self._promote_personal_intent(
                    prediction,
                    personal_context,
                )
            )

        if prediction.intent is Intent.IGNORE:

            result = (
                self._build_ignore_response(
                    prediction,
                    guard_result,
                    prepared,
                )
            )

        elif (
            prediction.intent
            is Intent.GENERAL_CHAT
        ):

            result = (
                self._build_general_chat_response(
                    prepared.resolved_query,
                    prediction,
                    guard_result,
                    prepared,
                    original_question=question,
                    conversation_context=conversation_context,
                    persona_instruction=persona_instruction,
                )
            )

        else:

            result = self._build_rag_response(
                prepared.resolved_query,
                query_embedding,
                prediction,
                guard_result,
                prepared,
                personal_context=personal_context,
                original_question=question,
                conversation_context=conversation_context,
                persona_instruction=persona_instruction,
            )

        return self._with_summary(
            result,
            question,
            history,
            summary,
        )

    def stream_answer(
        self,
        question: str,
        history=(),
        summary: str = "",
        *,
        persona: str = "coach",
        confirmation_id: str = "",
        confirmation_answer: bool | None = None,
        personal_context_loader: Callable[
            [str, list[dict]],
            str | None,
        ] | None = None,
    ) -> Iterator[ChatStreamEvent]:

        persona_instruction = (
            get_chatbot_persona_instruction(
                persona
            )
        )

        yield ChatStreamEvent(
            event="progress",
            stage="prepare_query",
        )

        prepared = self._prepare_query(
            question,
            history,
            summary,
            confirmation_id=confirmation_id,
            confirmation_answer=confirmation_answer,
        )

        conversation_context = (
            self._format_recent_context(
                history
            )
        )

        guard_result = (
            self._combined_guard(
                question,
                prepared.resolved_query,
            )
        )

        if prepared.blocked_answer:

            result = (
                self._build_query_blocked_response(
                    prepared,
                    guard_result,
                )
            )

            yield from (
                self._stream_fixed_result(
                    self._with_summary(
                        result,
                        question,
                        history,
                        summary,
                    )
                )
            )

            return

        if self._intent_classifier is None:
            raise (
                IntentClassifierUnavailableError(
                    "학습된 intent 모델이 없어 "
                    "챗봇 경로를 선택할 수 없습니다."
                )
            )

        yield ChatStreamEvent(
            event="progress",
            stage="classify_intent",
        )

        query_embedding = (
            self._vector_search.embed_query(
                prepared.resolved_query
            )
        )

        prediction = (
            self._intent_classifier.predict(
                query_embedding
            )
        )

        personal_context = None

        if self._should_load_personal_context(
            prepared,
            prediction,
            personal_context_loader,
            history,
            summary,
        ):

            yield ChatStreamEvent(
                event="progress",
                stage="load_health_context",
            )

            personal_context = (
                personal_context_loader(
                    prepared.standalone_question,
                    prepared.resolved_terms,
                )
            )

            prediction = (
                self._promote_personal_intent(
                    prediction,
                    personal_context,
                )
            )

        if prediction.intent is Intent.IGNORE:

            yield from self._stream_fixed_result(
                self._with_summary(
                    self._build_ignore_response(
                        prediction,
                        guard_result,
                        prepared,
                    ),
                    question,
                    history,
                    summary,
                )
            )

            return

        if (
            prediction.intent
            is Intent.GENERAL_CHAT
        ):

            yield ChatStreamEvent(
                event="progress",
                stage="generate_answer",
            )

            for event in (
                self._stream_general_chat_response(
                    prepared.resolved_query,
                    prediction,
                    guard_result,
                    prepared,
                    original_question=question,
                    conversation_context=conversation_context,
                    persona_instruction=persona_instruction,
                )
            ):

                if event.event == "complete":

                    yield ChatStreamEvent(
                        event="progress",
                        stage="summarize_conversation",
                    )

                yield (
                    self._summarized_stream_event(
                        event,
                        question,
                        history,
                        summary,
                    )
                )

            return

        yield ChatStreamEvent(
            event="progress",
            stage="search_evidence",
        )

        for event in self._stream_rag_response(
            prepared.resolved_query,
            query_embedding,
            prediction,
            guard_result,
            prepared,
            personal_context=personal_context,
            original_question=question,
            conversation_context=conversation_context,
            persona_instruction=persona_instruction,
        ):

            if event.event == "complete":

                yield ChatStreamEvent(
                    event="progress",
                    stage="summarize_conversation",
                )

            yield self._summarized_stream_event(
                event,
                question,
                history,
                summary,
            )

    def _prepare_query(
        self,
        question: str,
        history,
        summary: str,
        *,
        confirmation_id: str,
        confirmation_answer: bool | None,
    ) -> PreparedQuery:

        original = str(
            question
        ).strip()

        if confirmation_id:

            return (
                self._prepare_confirmed_query(
                    original,
                    confirmation_id,
                    confirmation_answer,
                )
            )

        rewrite = (
            self._query_rewriter.rewrite(
                original,
                history,
                summary,
            )
            if self._query_rewriter
            is not None
            else QueryRewriteResult(
                question=original,
                original_question=original,
                rewritten=False,
                reason=(
                    "질문 재작성 기능을 "
                    "사용하지 않습니다."
                ),
            )
        )

        standalone = rewrite.question

        resolution_error = None

        try:

            resolution = (
                self._query_resolver.resolve(
                    standalone
                )
                if self._query_resolver
                is not None
                else QueryResolution(
                    standalone,
                    standalone,
                )
            )

        except Exception as exc:

            resolution = QueryResolution(
                standalone,
                standalone,
            )

            resolution_error = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        terms = [
            term.as_dict()
            for term in resolution.terms
        ]

        confirmation_key = ""

        blocked_answer = ""

        if resolution.needs_confirmation:

            if (
                self._confirmation_store
                is not None
            ):
                confirmation_key = (
                    self._confirmation_store.create(
                        standalone,
                        terms,
                    )
                )

            blocked_answer = (
                resolution.confirmation_question
            )

        elif (
            resolution.resolution_status
            == "AMBIGUOUS"
        ):

            blocked_answer = (
                "입력하신 검색어가 여러 건강정보 "
                "항목으로 해석될 수 있어요. "
                "질환명이나 검사명을 조금 더 "
                "정확하게 입력해 주세요."
            )

        return PreparedQuery(
            original_question=original,
            standalone_question=standalone,
            resolved_query=resolution.resolved_query,
            query_rewritten=rewrite.rewritten,
            rewrite_reason=rewrite.reason,
            rewrite_error=rewrite.error,
            is_follow_up=rewrite.is_follow_up,
            current_topic=rewrite.current_topic,
            inherited_target=rewrite.inherited_target,
            personal_context_required=rewrite.personal_context_required,
            context_analysis_performed=rewrite.context_analysis_performed,
            resolved_terms=terms,
            resolution_status=resolution.resolution_status,
            resolution_error=resolution_error,
            query_confirmation=resolution.needs_confirmation,
            confirmation_question=resolution.confirmation_question,
            confirmation_id=confirmation_key,
            blocked_answer=blocked_answer,
        )

    def _prepare_confirmed_query(
        self,
        original: str,
        confirmation_id: str,
        confirmation_answer: bool | None,
    ) -> PreparedQuery:

        record = (
            self._confirmation_store.consume(
                confirmation_id
            )
            if self._confirmation_store
            is not None
            else None
        )

        if record is None:

            return PreparedQuery(
                original_question=original,
                standalone_question=original,
                resolved_query=original,
                resolution_status=(
                    "CONFIRMATION_EXPIRED"
                ),
                blocked_answer=(
                    "용어 확인 요청이 만료되었거나 "
                    "이미 사용되었습니다. "
                    "질문을 다시 입력해 주세요."
                ),
            )

        if confirmation_answer is not True:

            return PreparedQuery(
                original_question=original,
                standalone_question=(
                    record.original_question
                ),
                resolved_query=(
                    record.original_question
                ),
                resolution_status=(
                    "CONFIRMATION_REJECTED"
                ),
                blocked_answer=(
                    "확인을 취소했습니다. "
                    "찾으시는 질환명, 검사명 또는 "
                    "약 이름을 조금 더 정확하게 "
                    "입력해 주세요."
                ),
            )

        resolution = (
            build_confirmed_query_resolution(
                record.original_question,
                record.term,
            )
        )

        return PreparedQuery(
            original_question=original,
            standalone_question=(
                record.original_question
            ),
            resolved_query=(
                resolution.resolved_query
            ),
            query_rewritten=(
                record.original_question
                != original
            ),
            rewrite_reason=(
                "이전 확인 요청의 독립형 "
                "질문을 재사용했습니다."
            ),
            resolved_terms=[
                term.as_dict()
                for term
                in resolution.terms
            ],
            resolution_status=(
                resolution.resolution_status
            ),
        )

    @staticmethod
    def _combined_guard(
        original: str,
        resolved: str,
    ) -> GuardResult:

        original_guard = (
            check_safety_guard(
                original
            )
        )

        resolved_guard = (
            check_safety_guard(
                resolved
            )
        )

        rank = {
            RiskLevel.NORMAL: 0,
            RiskLevel.CAUTION: 1,
            RiskLevel.EMERGENCY: 2,
        }

        risk_level = max(
            (
                original_guard.risk_level,
                resolved_guard.risk_level,
            ),
            key=rank.__getitem__,
        )

        restrictions = list(
            dict.fromkeys(
                original_guard.restricted_actions
                + resolved_guard.restricted_actions
            )
        )

        reasons = list(
            dict.fromkeys(
                reason
                for reason
                in (
                    original_guard.reason,
                    resolved_guard.reason,
                )
                if reason
            )
        )

        return GuardResult(
            triggered=(
                risk_level
                is not RiskLevel.NORMAL
            ),
            risk_level=risk_level,
            restricted_actions=restrictions,
            response_policy=(
                "emergency_first_grounded_guidance"
                if risk_level
                is RiskLevel.EMERGENCY
                else "grounded_safe_guidance"
                if risk_level
                is RiskLevel.CAUTION
                else "standard_grounded"
            ),
            emergency=(
                risk_level
                is RiskLevel.EMERGENCY
            ),
            reason=(
                "|".join(
                    reasons
                )
                or None
            ),
            matched_patterns=list(
                dict.fromkeys(
                    original_guard.matched_patterns
                    + resolved_guard.matched_patterns
                )
            ),
        )

    @staticmethod
    def _query_fields(
        prepared: PreparedQuery,
    ) -> dict:

        return {
            "original_question": (
                prepared.original_question
            ),
            "standalone_question": (
                prepared.standalone_question
            ),
            "resolved_query": (
                prepared.resolved_query
            ),
            "query_rewritten": (
                prepared.query_rewritten
            ),
            "rewrite_reason": (
                prepared.rewrite_reason
            ),
            "rewrite_error": (
                prepared.rewrite_error
            ),
            "is_follow_up": (
                prepared.is_follow_up
            ),
            "current_topic": (
                prepared.current_topic
            ),
            "inherited_target": (
                prepared.inherited_target
            ),
            "personal_context_required": (
                prepared.personal_context_required
            ),
            "resolved_terms": (
                prepared.resolved_terms
            ),
            "resolution_status": (
                prepared.resolution_status
            ),
            "resolution_error": (
                prepared.resolution_error
            ),
            "query_confirmation": (
                prepared.query_confirmation
            ),
            "confirmation_question": (
                prepared.confirmation_question
            ),
            "confirmation_id": (
                prepared.confirmation_id
            ),
        }

    @staticmethod
    def _format_recent_context(
        history,
    ) -> str:

        return (
            format_history(
                normalize_history(
                    history
                )
            )
            or "(없음)"
        )

    def _with_summary(
        self,
        result: ChatOrchestrationResult,
        question: str,
        history,
        summary: str,
    ) -> ChatOrchestrationResult:

        previous = (
            summary
            or ""
        ).strip()

        if (
            result.query_confirmation
            or result.verification_method
            in {
                "query_ambiguity",
                "query_confirmation_expired",
                "query_confirmation_rejected",
            }
        ):

            return replace(
                result,
                conversation_summary=previous,
                summary_reason=(
                    "용어 확인 단계에서는 "
                    "대화 요약을 갱신하지 않습니다."
                ),
            )

        if (
            self._conversation_summarizer
            is None
        ):

            return replace(
                result,
                conversation_summary=previous,
                summary_reason=(
                    "대화 요약 기능을 "
                    "사용하지 않습니다."
                ),
            )

        turns = normalize_history(
            history
        )

        turns += normalize_history(
            [
                {
                    "role": "user",
                    "content": question,
                },
                {
                    "role": "assistant",
                    "content": result.answer,
                },
            ]
        )

        update = (
            self._conversation_summarizer.update(
                previous,
                select_evicted_turns(
                    turns
                ),
            )
        )

        return replace(
            result,
            conversation_summary=(
                update.summary
            ),
            summary_updated=(
                update.updated
            ),
            summary_reason=(
                update.reason
            ),
        )

    def _summarized_stream_event(
        self,
        event: ChatStreamEvent,
        question: str,
        history,
        summary: str,
    ) -> ChatStreamEvent:

        if (
            event.event != "complete"
            or event.result is None
        ):
            return event

        return ChatStreamEvent(
            event="complete",
            result=self._with_summary(
                event.result,
                question,
                history,
                summary,
            ),
        )

    @staticmethod
    def _should_load_personal_context(
        prepared: PreparedQuery,
        prediction: IntentPrediction,
        loader: Callable[
            [str, list[dict]],
            str | None,
        ] | None,
        history=(),
        summary: str = "",
    ) -> bool:

        if loader is None:
            return False

        if (
            prepared.context_analysis_performed
            and prepared.personal_context_required
        ):
            return True

        if (
            prediction.intent
            is Intent.COMPREHENSIVE
        ):
            return True

        if (
            prediction.intent
            is not Intent.SIMPLE_LOOKUP
        ):
            return False

        if (
            prepared.context_analysis_performed
        ):
            return False

        current_questions = (
            prepared.original_question,
            prepared.standalone_question,
            prepared.resolved_query,
        )

        return any(
            PERSONAL_HEALTH_QUESTION_PATTERN.search(
                question
            )
            for question
            in current_questions
        )

    @staticmethod
    def _promote_personal_intent(
        prediction: IntentPrediction,
        personal_context: str | None,
    ) -> IntentPrediction:

        if (
            not personal_context
            or prediction.intent
            is Intent.COMPREHENSIVE
        ):
            return prediction

        return replace(
            prediction,
            intent=Intent.COMPREHENSIVE,
        )

    @staticmethod
    def _prediction_fields(
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> dict:

        model_intent = max(
            prediction.probabilities,
            key=(
                prediction
                .probabilities
                .get
            ),
            default=(
                prediction.intent.value
            ),
        )

        return {
            "intent": (
                prediction.intent
            ),
            "confidence": (
                prediction.confidence
            ),
            "probabilities": (
                prediction.probabilities
            ),
            "uncertain": (
                prediction.uncertain
            ),
            "model_version": (
                prediction.model_version
            ),
            "intent_source": (
                "personal_health_context_override"
                if model_intent
                != prediction.intent.value
                else "linear_classifier"
            ),
            "guard_triggered": (
                guard_result.triggered
            ),
            "guard_reason": (
                guard_result.reason
            ),
            "matched_patterns": (
                guard_result.matched_patterns
            ),
            "risk_level": (
                guard_result.risk_level.value
            ),
            "restricted_actions": (
                guard_result.restricted_actions
            ),
            "response_policy": (
                guard_result.response_policy
            ),
            "emergency": (
                guard_result.emergency
            ),
        }

    def _build_query_blocked_response(
        self,
        prepared: PreparedQuery,
        guard_result: GuardResult,
    ) -> ChatOrchestrationResult:

        probabilities = {
            intent.value: 0.0
            for intent in Intent
        }

        probabilities[
            Intent.SIMPLE_LOOKUP.value
        ] = 1.0

        method = {
            "CONFIRM": (
                "query_confirmation"
            ),
            "AMBIGUOUS": (
                "query_ambiguity"
            ),
            "CONFIRMATION_EXPIRED": (
                "query_confirmation_expired"
            ),
            "CONFIRMATION_REJECTED": (
                "query_confirmation_rejected"
            ),
        }.get(
            prepared.resolution_status,
            "query_resolution",
        )

        return ChatOrchestrationResult(
            intent=Intent.SIMPLE_LOOKUP,
            confidence=1.0,
            probabilities=probabilities,
            uncertain=False,
            model_version=(
                self._intent_classifier.model_version
                if self._intent_classifier
                is not None
                else "not_run"
            ),
            intent_source="query_resolver",
            guard_triggered=(
                guard_result.triggered
            ),
            guard_reason=(
                guard_result.reason
            ),
            matched_patterns=(
                guard_result.matched_patterns
            ),
            risk_level=(
                guard_result.risk_level.value
            ),
            restricted_actions=(
                guard_result.restricted_actions
            ),
            response_policy=(
                guard_result.response_policy
            ),
            emergency=(
                guard_result.emergency
            ),
            **self._query_fields(
                prepared
            ),
            answer=(
                prepared.blocked_answer
            ),
            grounded=None,
            verification_method=method,
            verification_reason=(
                "query_resolver:"
                f"{prepared.resolution_status.lower()}"
            ),
            audit_status="not_applicable",
            audit_summary=(
                "검색 전에 의료용어 "
                "입력을 확인합니다."
            ),
        )

    def _build_ignore_response(
        self,
        prediction: IntentPrediction,
        guard_result: GuardResult,
        prepared: PreparedQuery,
    ) -> ChatOrchestrationResult:

        return ChatOrchestrationResult(
            **self._prediction_fields(
                prediction,
                guard_result,
            ),
            **self._query_fields(
                prepared
            ),
            answer=(
                GENERAL_IGNORE_ANSWER
            ),
            grounded=None,
            verification_method=(
                "fixed_response"
            ),
            verification_reason=(
                "intent:ignore"
            ),
        )

    def _build_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
        guard_result: GuardResult,
        prepared: PreparedQuery,
        *,
        original_question: str,
        conversation_context: str,
        persona_instruction: str,
    ) -> ChatOrchestrationResult:

        answer = str(
            self._general_chat_chain.invoke(
                {
                    "question": question,
                    "original_question": (
                        original_question
                    ),
                    "conversation_context": (
                        conversation_context
                    ),
                    "persona_instruction": (
                        persona_instruction
                    ),
                }
            )
        ).strip()

        return ChatOrchestrationResult(
            **self._prediction_fields(
                prediction,
                guard_result,
            ),
            **self._query_fields(
                prepared
            ),
            answer=answer,
            grounded=None,
            verification_method=(
                "not_applicable"
            ),
            verification_reason=(
                "intent:general_chat"
            ),
        )

    def _stream_general_chat_response(
        self,
        question: str,
        prediction: IntentPrediction,
        guard_result: GuardResult,
        prepared: PreparedQuery,
        *,
        original_question: str,
        conversation_context: str,
        persona_instruction: str,
    ) -> Iterator[ChatStreamEvent]:

        answer_parts: list[str] = []

        for token in (
            self._general_chat_chain.stream(
                {
                    "question": question,
                    "original_question": (
                        original_question
                    ),
                    "conversation_context": (
                        conversation_context
                    ),
                    "persona_instruction": (
                        persona_instruction
                    ),
                }
            )
        ):

            text = str(
                token
            )

            if not text:
                continue

            answer_parts.append(
                text
            )

            yield ChatStreamEvent(
                event="token",
                text=text,
            )

        yield ChatStreamEvent(
            event="progress",
            stage="answer_stream_complete",
        )

        result = (
            ChatOrchestrationResult(
                **self._prediction_fields(
                    prediction,
                    guard_result,
                ),
                **self._query_fields(
                    prepared
                ),
                answer="".join(
                    answer_parts
                ).strip(),
                grounded=None,
                verification_method=(
                    "not_applicable"
                ),
                verification_reason=(
                    "intent:general_chat"
                ),
            )
        )

        yield ChatStreamEvent(
            event="complete",
            result=result,
        )

    def _build_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
        guard_result: GuardResult,
        prepared: PreparedQuery,
        *,
        personal_context: str | None = None,
        original_question: str,
        conversation_context: str,
        persona_instruction: str,
    ) -> ChatOrchestrationResult:

        (
            documents,
            searched_collections,
            failed_collections,
        ) = self._search_rag_documents(
            query_embedding
        )

        verification_reason = (
            self._verification_reason(
                prediction,
                guard_result,
            )
        )

        grounded_result: GroundedAnswerResult = (
            self._grounded_rag_service.answer(
                question,
                documents,
                safety_policy=guard_result,
                audit=False,
                personal_context=(
                    personal_context
                    or ""
                ),
                original_question=(
                    original_question
                ),
                conversation_context=(
                    conversation_context
                ),
                persona_instruction=(
                    persona_instruction
                ),
            )
        )

        return ChatOrchestrationResult(
            **self._prediction_fields(
                prediction,
                guard_result,
            ),
            **self._query_fields(
                prepared
            ),
            answer=grounded_result.answer,
            grounded=grounded_result.grounded,
            documents=documents,
            cited_chunk_ids=(
                grounded_result.cited_chunk_ids
            ),
            verification_method=(
                grounded_result
                .verification_method
            ),
            verification_reason=(
                verification_reason
            ),
            grounding_errors=(
                grounded_result
                .grounding_errors
            ),
            unsupported_claims=(
                grounded_result
                .unsupported_claims
            ),
            evidence_status=(
                grounded_result
                .evidence_status
            ),
            retrieval_assessment=(
                grounded_result
                .retrieval_assessment
                .__dict__
            ),
            audit_status=(
                grounded_result
                .audit_status
            ),
            audit_summary=(
                grounded_result
                .audit_summary
            ),
            unanswered_items=(
                grounded_result
                .unanswered_items
                or []
            ),
            safety_violations=(
                grounded_result
                .safety_violations
                or []
            ),
            searched_collections=(
                searched_collections
            ),
            failed_collections=(
                failed_collections
            ),
            personal_context_used=(
                bool(
                    personal_context
                )
            ),
        )

    def _stream_rag_response(
        self,
        question: str,
        query_embedding: list[float],
        prediction: IntentPrediction,
        guard_result: GuardResult,
        prepared: PreparedQuery,
        *,
        personal_context: str | None = None,
        original_question: str,
        conversation_context: str,
        persona_instruction: str,
    ) -> Iterator[ChatStreamEvent]:

        (
            documents,
            searched_collections,
            failed_collections,
        ) = self._search_rag_documents(
            query_embedding
        )

        verification_reason = (
            self._verification_reason(
                prediction,
                guard_result,
            )
        )

        yield ChatStreamEvent(
            event="progress",
            stage="generate_answer",
        )

        for event in (
            self._grounded_rag_service
            .stream_answer(
                question,
                documents,
                safety_policy=(
                    guard_result
                ),
                audit=False,
                personal_context=(
                    personal_context
                    or ""
                ),
                original_question=(
                    original_question
                ),
                conversation_context=(
                    conversation_context
                ),
                persona_instruction=(
                    persona_instruction
                ),
            )
        ):

            if isinstance(
                event,
                str,
            ):
                yield ChatStreamEvent(
                    event="token",
                    text=event,
                )
                continue

            if isinstance(
                event,
                GroundedRagProgress,
            ):
                yield ChatStreamEvent(
                    event="progress",
                    stage=event.stage,
                )
                continue

            result = ChatOrchestrationResult(
                **self._prediction_fields(
                    prediction,
                    guard_result,
                ),
                **self._query_fields(
                    prepared
                ),
                answer=event.answer,
                grounded=event.grounded,
                documents=documents,
                cited_chunk_ids=(
                    event.cited_chunk_ids
                ),
                verification_method=(
                    event.verification_method
                ),
                verification_reason=(
                    verification_reason
                ),
                grounding_errors=(
                    event.grounding_errors
                ),
                unsupported_claims=(
                    event.unsupported_claims
                ),
                evidence_status=(
                    event.evidence_status
                ),
                retrieval_assessment=(
                    event
                    .retrieval_assessment
                    .__dict__
                ),
                audit_status=(
                    event.audit_status
                ),
                audit_summary=(
                    event.audit_summary
                ),
                unanswered_items=(
                    event.unanswered_items
                    or []
                ),
                safety_violations=(
                    event.safety_violations
                    or []
                ),
                searched_collections=(
                    searched_collections
                ),
                failed_collections=(
                    failed_collections
                ),
                personal_context_used=(
                    bool(
                        personal_context
                    )
                ),
            )

            yield ChatStreamEvent(
                event="complete",
                result=result,
            )

    @staticmethod
    def _verification_reason(
        prediction: IntentPrediction,
        guard_result: GuardResult,
    ) -> str:

        intent_reason = (
            "intent_uncertain"
            if prediction.uncertain
            else (
                f"intent:"
                f"{prediction.intent.value}"
            )
        )

        if (
            guard_result.risk_level
            is RiskLevel.NORMAL
        ):
            return intent_reason

        return (
            f"{intent_reason}|"
            f"risk:"
            f"{guard_result.risk_level.value}"
        )

    def _search_rag_documents(
        self,
        query_embedding: list[float],
    ) -> tuple[
        list[Document],
        list[str],
        list[str],
    ]:

        search_result = (
            self._vector_search
            .search_many_by_vector(
                self._search_collections,
                query_embedding,
                self._top_k_per_collection,
            )
        )

        if (
            search_result.errors
            and len(
                search_result.errors
            )
            == len(
                search_result
                .searched_collections
            )
        ):

            raise SearchUnavailableError(
                "모든 Pinecone namespace "
                "검색에 실패했습니다."
            )

        documents = (
            merge_search_results(
                search_result.documents,
                final_top_k=(
                    self._final_top_k
                ),
                max_per_collection=(
                    self._max_per_collection
                ),
                min_score=(
                    self._min_score
                ),
            )
        )

        return (
            documents,
            search_result.searched_collections,
            sorted(
                search_result.errors
            ),
        )

    @staticmethod
    def _stream_fixed_result(
        result: ChatOrchestrationResult,
    ) -> Iterator[ChatStreamEvent]:

        yield ChatStreamEvent(
            event="token",
            text=result.answer,
        )

        yield ChatStreamEvent(
            event="progress",
            stage="answer_stream_complete",
        )

        yield ChatStreamEvent(
            event="complete",
            result=result,
        )