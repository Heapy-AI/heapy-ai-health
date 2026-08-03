"""다중 Pinecone namespace 검색 결과 병합 규칙.

작성자: 김진우
"""
from __future__ import annotations

import hashlib
import re

from langchain_core.documents import Document


def _normalized_text(value: str) -> str:
    """공백 차이를 제거한 중복 판정용 본문을 만든다."""
    return re.sub(r"\s+", " ", value).strip()


def _deduplication_key(document: Document) -> str:
    """namespace가 달라도 같은 원천 청크면 동일한 키를 반환한다."""
    metadata = document.metadata
    source_id = str(
        metadata.get("source_id")
        or metadata.get("document_id")
        or metadata.get("source")
        or ""
    ).strip()
    chunk_id = str(metadata.get("chunk_id") or "").strip()

    if source_id and chunk_id:
        return f"source:{source_id}|chunk:{chunk_id}"

    normalized = _normalized_text(document.page_content)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"text:{digest}"


def merge_search_results(
    documents: list[Document],
    *,
    final_top_k: int,
    max_per_collection: int,
    min_score: float,
) -> list[Document]:
    """후보를 중복 제거·정렬하고 컬렉션 편중을 제한한다."""
    if final_top_k <= 0:
        raise ValueError("final_top_k는 1 이상이어야 합니다.")
    if max_per_collection <= 0:
        raise ValueError("max_per_collection은 1 이상이어야 합니다.")
    if min_score < 0.0:
        raise ValueError("min_score는 0 이상이어야 합니다.")

    ranked = sorted(
        documents,
        key=lambda document: (
            -float(document.metadata.get("score", 0.0) or 0.0),
            str(document.metadata.get("collection", "")),
            str(document.metadata.get("record_id", "")),
        ),
    )

    selected: list[Document] = []
    seen: set[str] = set()
    collection_counts: dict[str, int] = {}

    for document in ranked:
        score = float(document.metadata.get("score", 0.0) or 0.0)
        collection = str(document.metadata.get("collection", "")).strip()
        if not collection or score < min_score:
            continue

        deduplication_key = _deduplication_key(document)
        if deduplication_key in seen:
            continue

        current_count = collection_counts.get(collection, 0)
        if current_count >= max_per_collection:
            continue

        selected.append(document)
        seen.add(deduplication_key)
        collection_counts[collection] = current_count + 1
        if len(selected) >= final_top_k:
            break

    return selected
