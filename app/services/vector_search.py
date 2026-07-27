"""로컬 임베딩과 Pinecone dense 인덱스를 사용하는 검색 서비스.

작성자: 김진우
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.documents import Document

from app.core.config import (
    COLLECTIONS,
    EMBED_MODEL,
    PINECONE_API_KEY,
    PINECONE_DIMENSION,
    PINECONE_INDEX_NAME,
    PINECONE_METRIC,
)


def _read_value(value: Any, key: str, default: Any = None) -> Any:
    """Pinecone SDK 응답의 객체·딕셔너리 표현을 모두 읽는다."""
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


class PineconeSearchService:
    """질문을 로컬 임베딩한 뒤 Pinecone namespace에서 검색한다."""

    backend_name = "pinecone"
    embed_model = EMBED_MODEL

    def __init__(self) -> None:
        if not PINECONE_API_KEY:
            raise RuntimeError(
                "PINECONE_API_KEY가 없습니다. 프로젝트 루트의 .env 파일을 확인하세요."
            )
        if not PINECONE_INDEX_NAME:
            raise RuntimeError("PINECONE_INDEX_NAME은 빈 문자열일 수 없습니다.")

        from langchain_huggingface import HuggingFaceEmbeddings
        from pinecone import Pinecone

        client = Pinecone(api_key=PINECONE_API_KEY)
        if not client.has_index(PINECONE_INDEX_NAME):
            raise RuntimeError(f"Pinecone 인덱스가 없습니다: {PINECONE_INDEX_NAME}")

        description = client.describe_index(PINECONE_INDEX_NAME)
        status = _read_value(description, "status", {})
        if not bool(_read_value(status, "ready", False)):
            state = _read_value(status, "state", "알 수 없음")
            raise RuntimeError(f"Pinecone 인덱스가 준비되지 않았습니다: {state}")

        dimension = int(_read_value(description, "dimension", 0) or 0)
        metric = str(_read_value(description, "metric", "")).lower()
        if dimension != PINECONE_DIMENSION or metric != PINECONE_METRIC:
            raise RuntimeError(
                f"Pinecone 인덱스 설정이 올바르지 않습니다: "
                f"dimension={dimension}, metric={metric} "
                f"(필요: {PINECONE_DIMENSION}, {PINECONE_METRIC})"
            )

        host = _read_value(description, "host")
        if not host:
            raise RuntimeError(
                f"Pinecone 인덱스 host를 확인할 수 없습니다: {PINECONE_INDEX_NAME}"
            )

        self._index = client.Index(host=host)
        self._embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    def embed_query(self, question: str) -> list[float]:
        """질문을 검색·분류에서 재사용할 768차원 벡터로 변환한다."""
        query_vector = self._embeddings.embed_query(question)
        if len(query_vector) != PINECONE_DIMENSION:
            raise ValueError(
                f"질문 임베딩 차원이 올바르지 않습니다: "
                f"{len(query_vector)} != {PINECONE_DIMENSION}"
            )
        return query_vector

    def search_by_vector(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[Document]:
        """이미 계산한 질문 벡터로 지정 namespace를 검색한다."""
        if len(query_vector) != PINECONE_DIMENSION:
            raise ValueError(
                f"질문 임베딩 차원이 올바르지 않습니다: "
                f"{len(query_vector)} != {PINECONE_DIMENSION}"
            )

        response = self._index.query(
            namespace=collection,
            vector=query_vector,
            top_k=top_k,
            include_values=False,
            include_metadata=True,
        )

        documents: list[Document] = []
        for match in _read_value(response, "matches", []) or []:
            metadata = dict(_read_value(match, "metadata", {}) or {})
            page_content = str(metadata.pop("chunk_text", "")).strip()
            if not page_content:
                continue

            metadata["record_id"] = str(_read_value(match, "id", ""))
            metadata["score"] = float(_read_value(match, "score", 0.0) or 0.0)
            documents.append(Document(page_content=page_content, metadata=metadata))
        return documents

    def search(self, collection: str, question: str, top_k: int) -> list[Document]:
        """질문을 임베딩한 뒤 지정 namespace에서 유사 청크를 반환한다."""
        query_vector = self.embed_query(question)
        return self.search_by_vector(collection, query_vector, top_k)

    def counts(self) -> dict[str, int]:
        """namespace별 적재 벡터 수를 반환한다."""
        stats = self._index.describe_index_stats()
        namespaces = _read_value(stats, "namespaces", {}) or {}
        result: dict[str, int] = {}

        for collection in COLLECTIONS:
            namespace = _read_value(namespaces, collection, {})
            result[collection] = int(
                _read_value(namespace, "vector_count", 0) or 0
            )
        return result


def build_pinecone_search_service() -> PineconeSearchService:
    """FastAPI lifespan에서 공유할 Pinecone 검색 서비스를 생성한다."""
    return PineconeSearchService()
