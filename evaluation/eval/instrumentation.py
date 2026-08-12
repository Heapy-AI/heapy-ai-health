"""운영 경로(ChatOrchestrator)를 그대로 쓰면서 단계별 처리시간을 계측한다.

무거운 자원(임베딩 모델, Pinecone 인덱스, Gemini 체인)은 한 번만 만들어 공유하고,
질문마다 가벼운 계측 래퍼로 감싼 ChatOrchestrator를 새로 조립한다.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from time import perf_counter

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import (
    INTENT_MIN_CONFIDENCE,
    INTENT_MODEL_PATH,
    MODEL,
    SEARCH_COLLECTIONS,
    SEARCH_FINAL_TOP_K,
    SEARCH_MAX_PER_COLLECTION,
    SEARCH_MIN_SCORE,
    SEARCH_TOP_K_PER_COLLECTION,
)
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.general_chat import build_general_chat_chain
from app.services.grounded_rag import (
    GROUNDING_PLAN_PROMPT,
    FINAL_ANSWER_PROMPT,
    POST_AUDIT_PROMPT,
    GroundedRagService,
    GroundingAudit,
    GroundingPlan,
)
from app.services.intent_classifier import LinearIntentClassifier
from app.services.vector_search import (
    MultiCollectionSearchResult,
    build_pinecone_search_service,
)


def _ms(start: float) -> float:
    return (perf_counter() - start) * 1000.0


@dataclass
class StageTimings:
    """질문 1건의 단계별 소요 시간(ms)과 중간 산출물."""

    embed_ms: float | None = None
    intent_ms: float | None = None
    search_ms: float | None = None
    plan_ms: float | None = None
    generate_ttfb_ms: float | None = None
    generate_total_ms: float | None = None
    audit_ms: float | None = None
    end_to_end_ms: float | None = None
    first_token_ms: float | None = None
    raw_search: MultiCollectionSearchResult | None = None
    plan_error: str | None = None
    audit_error: str | None = None
    llm_calls: int = 0
    stream_chunks: int = 0

    def as_dict(self) -> dict:
        return {
            "embed_ms": self.embed_ms,
            "intent_ms": self.intent_ms,
            "search_ms": self.search_ms,
            "plan_ms": self.plan_ms,
            "generate_ttfb_ms": self.generate_ttfb_ms,
            "generate_total_ms": self.generate_total_ms,
            "audit_ms": self.audit_ms,
            "end_to_end_ms": self.end_to_end_ms,
            "first_token_ms": self.first_token_ms,
            "llm_calls": self.llm_calls,
            "stream_chunks": self.stream_chunks,
        }


class TimedVectorSearch:
    """임베딩·검색 호출 시간을 기록하는 PineconeSearchService 래퍼."""

    def __init__(self, inner, timings: StageTimings, lock: threading.Lock) -> None:
        self._inner = inner
        self._timings = timings
        self._lock = lock

    @property
    def backend_name(self) -> str:
        return self._inner.backend_name

    @property
    def embed_model(self) -> str:
        return self._inner.embed_model

    def embed_query(self, question: str) -> list[float]:
        start = perf_counter()
        # 로컬 임베딩은 GPU/CPU 상태를 공유하므로 직렬화해 계측 왜곡을 줄인다.
        with self._lock:
            vector = self._inner.embed_query(question)
        self._timings.embed_ms = _ms(start)
        return vector

    def search_many_by_vector(self, collections, query_vector, top_k_per_collection):
        start = perf_counter()
        result = self._inner.search_many_by_vector(
            collections, query_vector, top_k_per_collection
        )
        self._timings.search_ms = _ms(start)
        self._timings.raw_search = result
        return result


class TimedIntentClassifier:
    """분류 시간을 기록하는 LinearIntentClassifier 래퍼."""

    def __init__(self, inner: LinearIntentClassifier, timings: StageTimings) -> None:
        self._inner = inner
        self._timings = timings

    @property
    def model_version(self) -> str:
        return self._inner.model_version

    def predict(self, embedding):
        start = perf_counter()
        prediction = self._inner.predict(embedding)
        self._timings.intent_ms = _ms(start)
        return prediction


class TimedChain:
    """invoke/stream 시간을 기록하는 LangChain Runnable 래퍼."""

    def __init__(self, inner, timings: StageTimings, stage: str) -> None:
        self._inner = inner
        self._timings = timings
        self._stage = stage

    def invoke(self, values):
        start = perf_counter()
        try:
            result = self._inner.invoke(values)
        except Exception as exc:
            setattr(self._timings, f"{self._stage}_error", f"{type(exc).__name__}: {exc}")
            setattr(self._timings, f"{self._stage}_ms", _ms(start))
            raise
        setattr(self._timings, f"{self._stage}_ms", _ms(start))
        self._timings.llm_calls += 1
        return result

    def stream(self, values):
        start = perf_counter()
        first = True
        for token in self._inner.stream(values):
            if first:
                self._timings.generate_ttfb_ms = _ms(start)
                first = False
            self._timings.stream_chunks += 1
            yield token
        self._timings.generate_total_ms = _ms(start)
        self._timings.llm_calls += 1


@dataclass
class SharedServices:
    """모든 질문이 공유하는 무거운 자원."""

    vector_search: object
    intent_classifier: LinearIntentClassifier | None
    planner: object
    generator: object
    auditor: object
    general_chat_chain: object
    embed_lock: threading.Lock = field(default_factory=threading.Lock)
    model_name: str = MODEL

    @property
    def config_snapshot(self) -> dict:
        return {
            "llm_model": MODEL,
            "embed_model": self.vector_search.embed_model,
            "search_collections": list(SEARCH_COLLECTIONS),
            "top_k_per_collection": SEARCH_TOP_K_PER_COLLECTION,
            "final_top_k": SEARCH_FINAL_TOP_K,
            "max_per_collection": SEARCH_MAX_PER_COLLECTION,
            "min_score": SEARCH_MIN_SCORE,
            "intent_min_confidence": INTENT_MIN_CONFIDENCE,
            "intent_model_version": (
                self.intent_classifier.model_version
                if self.intent_classifier is not None
                else None
            ),
        }


def build_shared_services() -> SharedServices:
    """운영 lifespan과 동일한 구성으로 공유 자원을 만든다."""
    vector_search = build_pinecone_search_service()

    planner_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    generator_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    auditor_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    planner = (
        ChatPromptTemplate.from_template(GROUNDING_PLAN_PROMPT)
        | planner_llm.with_structured_output(GroundingPlan)
    )
    generator = (
        ChatPromptTemplate.from_template(FINAL_ANSWER_PROMPT)
        | generator_llm
        | StrOutputParser()
    )
    auditor = (
        ChatPromptTemplate.from_template(POST_AUDIT_PROMPT)
        | auditor_llm.with_structured_output(GroundingAudit)
    )

    intent_classifier = None
    if INTENT_MODEL_PATH.is_file():
        intent_classifier = LinearIntentClassifier.from_file(
            INTENT_MODEL_PATH, INTENT_MIN_CONFIDENCE
        )

    return SharedServices(
        vector_search=vector_search,
        intent_classifier=intent_classifier,
        planner=planner,
        generator=generator,
        auditor=auditor,
        general_chat_chain=build_general_chat_chain(),
    )


def build_instrumented_orchestrator(
    shared: SharedServices,
    timings: StageTimings,
) -> ChatOrchestrator:
    """질문 1건 전용 계측 오케스트레이터를 조립한다."""
    grounded_rag_service = GroundedRagService(
        TimedChain(shared.planner, timings, "plan"),
        TimedChain(shared.generator, timings, "generate"),
        TimedChain(shared.auditor, timings, "audit"),
        TimedChain(shared.generator, timings, "generate"),
    )
    return ChatOrchestrator(
        vector_search=TimedVectorSearch(
            shared.vector_search, timings, shared.embed_lock
        ),
        intent_classifier=(
            TimedIntentClassifier(shared.intent_classifier, timings)
            if shared.intent_classifier is not None
            else None
        ),
        grounded_rag_service=grounded_rag_service,
        general_chat_chain=shared.general_chat_chain,
        search_collections=SEARCH_COLLECTIONS,
        top_k_per_collection=SEARCH_TOP_K_PER_COLLECTION,
        final_top_k=SEARCH_FINAL_TOP_K,
        max_per_collection=SEARCH_MAX_PER_COLLECTION,
        min_score=SEARCH_MIN_SCORE,
    )
