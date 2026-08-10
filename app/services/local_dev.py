"""외부 API 없이 검색·오타 보정 흐름을 확인하는 로컬 데모 백엔드."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from langchain_core.documents import Document

from app.core.config import CHUNK_ROOT, PINECONE_DIMENSION, SEARCH_COLLECTIONS
from app.services.chat_orchestrator import (
    ChatOrchestrationResult,
    ChatOrchestrator,
)
from app.services.grounded_rag import (
    GroundedAnswerResult,
    GroundingPlan,
    GroundingPlanFact,
    NOT_GROUNDED_ANSWER,
)
from app.services.intent_classifier import (
    INTENT_LABELS,
    Intent,
    IntentPrediction,
)
from app.services.medical_term_catalog import build_term_catalog, load_jsonl_corpus
from app.services.query_resolver import (
    InMemoryMedicalTermRepository,
    MedicalQueryResolver,
    QueryResolution,
    normalize_search_text,
)
from app.services.vector_search import MultiCollectionSearchResult


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
LOCAL_QUERY_STOPWORDS = {"증상", "효능", "정보", "알려줘", "대해", "뭐야", "어때"}


@dataclass(frozen=True)
class _IndexedDocument:
    source: Document
    content_tokens: frozenset[str]
    metadata_tokens: frozenset[str]


def build_local_query_resolver() -> MedicalQueryResolver:
    """실제 workspace 문서에서만 로컬 표준용어 사전을 구성한다.

    의료용어를 코드에 직접 등록하지 않는다. corpus가 비어 있으면 빈
    저장소를 사용해 근거 없는 fallback 응답을 만들지 않는다.
    """
    terms = build_term_catalog(_load_workspace_corpus())
    return MedicalQueryResolver(InMemoryMedicalTermRepository(terms))


def _load_workspace_corpus() -> dict[str, list[Document]]:
    """현재 workspace의 JSONL 청크를 용어 목록 없이 로컬 검색에 연결한다.

    로컬 서버도 운영 인덱스에 적재할 원문을 기준으로 확인할 수 있어야 한다.
    여기서는 질환명·약품명 목록을 코드에 등록하지 않고, 각 청크의 text와
    metadata를 그대로 읽어 키워드 검색용 Document로 변환한다.
    """
    return load_jsonl_corpus(CHUNK_ROOT)


class LocalSearchService:
    """Pinecone 대신 로컬 문서와 키워드 점수를 사용하는 검색 서비스."""

    backend_name = "local_demo"
    embed_model = "local-keyword-demo"

    def __init__(self, query_resolver: MedicalQueryResolver) -> None:
        self._query_resolver = query_resolver
        # 실제 청크만 사용한다. corpus가 없으면 근거 없는 fallback을
        # 사용하지 않는다.
        self._corpus = _load_workspace_corpus()
        self._corpus_index = self._build_corpus_index(self._corpus)
        self._last_query = ""
        self._last_resolution: QueryResolution | None = None

    def resolve_query(self, question: str) -> QueryResolution:
        resolution = self._query_resolver.resolve(question)
        self._last_resolution = resolution
        return resolution

    def set_query_resolution(self, resolution: QueryResolution) -> None:
        """확인된 canonical term을 intent·검색 단계에서 재사용한다."""
        self._last_resolution = resolution

    def embed_resolved_query(self, resolved_question: str) -> list[float]:
        self._last_query = resolved_question
        return [0.0] * PINECONE_DIMENSION

    def embed_query(self, question: str) -> list[float]:
        resolution = self.resolve_query(question)
        return self.embed_resolved_query(resolution.resolved_query)

    @property
    def last_query(self) -> str:
        return self._last_query

    @property
    def last_resolution(self) -> QueryResolution | None:
        return self._last_resolution

    def search(self, collection: str, question: str, top_k: int) -> list[Document]:
        resolution = self.resolve_query(question)
        self.embed_resolved_query(resolution.resolved_query)
        documents = self._search_collection(
            collection,
            resolution.resolved_query,
            top_k,
            resolution=resolution,
        )
        self._attach_resolution(documents, resolution)
        return documents

    def search_many_by_vector(
        self,
        collections: tuple[str, ...] | list[str],
        query_vector: list[float],
        top_k_per_collection: int,
    ) -> MultiCollectionSearchResult:
        resolution = self._last_resolution or self.resolve_query(self._last_query)
        collections_to_search = self._collections_for_resolution(collections, resolution)
        documents = [
            document
            for collection in collections_to_search
            for document in self._search_collection(
                collection,
                self._last_query,
                top_k_per_collection,
                resolution=resolution,
            )
        ]
        return MultiCollectionSearchResult(
            documents=documents,
            searched_collections=list(collections_to_search),
            errors={},
        )

    def counts(self) -> dict[str, int]:
        return {collection: len(self._corpus.get(collection, [])) for collection in SEARCH_COLLECTIONS}

    def _search_collection(
        self,
        collection: str,
        query: str,
        top_k: int,
        *,
        resolution: QueryResolution | None = None,
    ) -> list[Document]:
        if (
            resolution is not None
            and resolution.domain_hint == "MEDICATION"
            and "medication" not in collection.casefold()
        ):
            return []
        query_key = normalize_search_text(query)
        query_tokens = {
            normalize_search_text(token)
            for token in TOKEN_RE.findall(query)
            if (
                len(normalize_search_text(token)) > 1
                and normalize_search_text(token) not in LOCAL_QUERY_STOPWORDS
            )
        }
        resolution_keys = {
            normalize_search_text(term.canonical_name)
            for term in (resolution.terms if resolution is not None else ())
            if normalize_search_text(term.canonical_name)
        }
        ranked: list[Document] = []
        for indexed in self._corpus_index.get(collection, ()):
            source = indexed.source
            metadata = source.metadata
            content_tokens = indexed.content_tokens
            metadata_tokens = indexed.metadata_tokens
            overlap = sum(
                token in content_tokens or token in metadata_tokens
                for token in query_tokens
            )
            score = min(0.99, 0.55 + 0.08 * overlap)
            if resolution_keys.intersection(metadata_tokens):
                score = 0.99
            elif query_key and query_key in metadata_tokens:
                score = 0.99
            elif query_key and query_key in content_tokens:
                score = 0.97
            elif not overlap:
                if (
                    resolution is None
                    or resolution.domain_hint != "MEDICATION"
                    or "medication" not in collection.casefold()
                ):
                    continue
                score = 0.60
            document = Document(
                page_content=source.page_content,
                metadata={**metadata, "score": score},
            )
            ranked.append(document)
        ranked.sort(
            key=lambda document: (
                -float(document.metadata.get("score", 0.0)),
                str(document.metadata.get("record_id", "")),
            )
        )
        return ranked[: max(1, top_k)]

    @staticmethod
    def _build_corpus_index(
        corpus: dict[str, list[Document]],
    ) -> dict[str, tuple[_IndexedDocument, ...]]:
        """문서별 토큰을 서버 시작 시 한 번만 계산한다."""
        indexed: dict[str, tuple[_IndexedDocument, ...]] = {}
        for collection, documents in corpus.items():
            items: list[_IndexedDocument] = []
            for source in documents:
                metadata = source.metadata
                aliases = metadata.get("aliases", [])
                if isinstance(aliases, str):
                    aliases = [aliases]
                metadata_text = " ".join(
                    [
                        str(metadata.get("canonical_key", "")),
                        str(metadata.get("record_id", "")),
                        str(metadata.get("disease", "")),
                        str(metadata.get("heading", "")),
                        " ".join(str(alias) for alias in aliases),
                    ]
                )
                items.append(
                    _IndexedDocument(
                        source=source,
                        content_tokens=frozenset(
                            normalize_search_text(token)
                            for token in TOKEN_RE.findall(source.page_content)
                        ),
                        metadata_tokens=frozenset(
                            normalize_search_text(token)
                            for token in TOKEN_RE.findall(metadata_text)
                        ),
                    )
                )
            indexed[collection] = tuple(items)
        return indexed

    @staticmethod
    def _collections_for_resolution(
        collections: tuple[str, ...] | list[str],
        resolution: QueryResolution,
    ) -> tuple[str, ...]:
        if resolution.domain_hint != "MEDICATION":
            return tuple(dict.fromkeys(collections))
        medication_collections = tuple(
            collection
            for collection in dict.fromkeys(collections)
            if "medication" in collection.casefold()
        )
        return medication_collections or tuple(dict.fromkeys(collections))

    @staticmethod
    def _attach_resolution(
        documents: list[Document],
        resolution: QueryResolution,
    ) -> None:
        for document in documents:
            document.metadata["original_query"] = resolution.original_query
            document.metadata["resolved_query"] = resolution.resolved_query
            document.metadata["resolved_terms"] = [
                term.as_dict() for term in resolution.terms
            ]


class LocalIntentClassifier:
    model_version = "local-demo-intent"

    def __init__(
        self,
        resolver: MedicalQueryResolver,
        query_provider: Callable[[], str] | None = None,
        resolution_provider: Callable[[], QueryResolution | None] | None = None,
    ) -> None:
        self._resolver = resolver
        self._query_provider = query_provider
        self._resolution_provider = resolution_provider

    def predict(self, embedding: list[float]) -> IntentPrediction:
        query = (
            self._query_provider()
            if self._query_provider is not None
            else getattr(self, "_last_query", "")
        )
        resolution = (
            self._resolution_provider()
            if self._resolution_provider is not None
            else self._resolver.resolve(query)
        )
        has_term = bool(resolution and resolution.terms) if query else False
        casual = bool(re.search(r"안녕|지쳐|피곤|스트레스|기분", query))
        intent = Intent.SIMPLE_LOOKUP if has_term or not casual else Intent.GENERAL_CHAT
        probabilities = {
            label: (0.94 if label == intent.value else 0.02)
            for label in INTENT_LABELS
        }
        return IntentPrediction(
            intent=intent,
            confidence=0.94,
            probabilities=probabilities,
            uncertain=False,
            model_version=self.model_version,
        )


class LocalGeneralChatChain:
    def invoke(self, values: dict) -> str:
        return "로컬 테스트 모드입니다. 건강정보 검색어를 입력하면 표준용어 보정과 검색 결과를 확인할 수 있어요."

    def stream(self, values: dict) -> Iterator[str]:
        yield from ("로컬 테스트 모드입니다. ", "건강정보 검색어를 입력해 보세요.")


class LocalAnswerChain:
    def invoke(self, values: dict) -> str:
        context = str(values.get("context", "")).strip()
        if not context:
            return NOT_GROUNDED_ANSWER
        return "[로컬 테스트 응답]\n" + context.split("\n\n", 1)[0]


class LocalGroundedRagService:
    def answer(
        self,
        question: str,
        documents: list[Document],
        *,
        verify_semantics: bool,
    ) -> GroundedAnswerResult:
        if not documents:
            return GroundedAnswerResult(
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                cited_chunk_ids=[],
                verification_method="local_demo_no_result",
                grounding_errors=["검색된 로컬 데모 문서가 없습니다."],
                unsupported_claims=[],
                audit_status="not_run",
                audit_summary="로컬 데모 문서가 없습니다.",
            )
        cited = [f"C{index}" for index in range(1, len(documents) + 1)]
        facts = [
            GroundingPlanFact(
                statement=documents[0].page_content,
                cited_chunk_ids=[cited[0]],
            )
        ]
        plan = GroundingPlan(
            answerable=True,
            facts=facts,
            reason="로컬 데모 문서가 표준화된 검색어와 매칭되었습니다.",
        )
        answer = f"[로컬 테스트 응답]\n{documents[0].page_content}\n\n검색 기준: {question}"
        return GroundedAnswerResult(
            answer=answer,
            grounded=True,
            cited_chunk_ids=cited,
            verification_method="local_demo_grounding",
            grounding_errors=[],
            unsupported_claims=[],
            grounding_plan=plan,
            audit_status="passed",
            audit_summary="로컬 데모 검색 문서를 사용했습니다.",
        )

    def stream_answer(
        self,
        question: str,
        documents: list[Document],
        *,
        verify_semantics: bool,
    ) -> Iterator[str | GroundedAnswerResult]:
        result = self.answer(question, documents, verify_semantics=verify_semantics)
        text = result.answer
        midpoint = max(1, len(text) // 2)
        yield text[:midpoint]
        yield text[midpoint:]
        yield result


def build_local_chat_orchestrator(
    vector_search: LocalSearchService,
    resolver: MedicalQueryResolver,
) -> ChatOrchestrator:
    """실제 오케스트레이터에 로컬 검색·응답 구현을 주입한다."""
    classifier = LocalIntentClassifier(
        resolver,
        query_provider=lambda: vector_search.last_query,
        resolution_provider=lambda: vector_search.last_resolution,
    )
    return ChatOrchestrator(
        vector_search=vector_search,
        intent_classifier=classifier,
        grounded_rag_service=LocalGroundedRagService(),
        general_chat_chain=LocalGeneralChatChain(),
        search_collections=SEARCH_COLLECTIONS,
        top_k_per_collection=3,
        final_top_k=6,
        max_per_collection=2,
        min_score=0.0,
    )
