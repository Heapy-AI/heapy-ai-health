"""문서 metadata에서 검색용 의료용어 사전을 만드는 공통 계층.

이 모듈은 특정 질환명이나 약품명을 코드에 등록하지 않는다. 원천 문서가
제공하는 표준명, metadata alias, ``관련어``만 읽어 용어 레코드를 만든다.
운영에서는 같은 레코드 모양을 RDB 적재 작업에서 사용하고, 로컬에서는
이 결과를 in-memory 저장소에 주입한다.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from app.services.query_resolver import normalize_search_text


RELATED_TERMS_PATTERN = re.compile(r"^\s*관련어\s*:\s*(.+)$", re.MULTILINE)


def load_jsonl_corpus(chunk_root: Path) -> dict[str, list[Document]]:
    """JSONL chunk 디렉터리를 공통 Document corpus로 읽는다."""
    corpus: dict[str, list[Document]] = {}
    if not chunk_root.is_dir():
        return corpus

    for collection_path in sorted(chunk_root.iterdir()):
        if not collection_path.is_dir():
            continue
        documents: list[Document] = []
        for jsonl_path in sorted(collection_path.glob("*.jsonl")):
            try:
                lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                try:
                    payload = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(payload, dict):
                    continue
                text = str(
                    payload.get("text") or payload.get("page_content") or ""
                ).strip()
                if not text:
                    continue
                raw_metadata = payload.get("metadata")
                metadata: dict[str, Any] = (
                    dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
                )
                aliases = _metadata_alias_values(metadata)
                for related_line in RELATED_TERMS_PATTERN.findall(text):
                    aliases.extend(
                        value.strip()
                        for value in re.split(r"[,，、;/|]", related_line)
                        if value.strip()
                    )
                if aliases:
                    metadata["aliases"] = list(dict.fromkeys(aliases))
                record_id = str(
                    payload.get("id")
                    or metadata.get("record_id")
                    or metadata.get("canonical_key")
                    or hashlib.sha1(
                        f"{jsonl_path}:{line_number}:{text}".encode("utf-8")
                    ).hexdigest()[:16]
                )
                metadata.update(
                    {
                        "collection": collection_path.name,
                        "record_id": record_id,
                        "source": str(
                            metadata.get("source") or f"local://{jsonl_path.name}"
                        ),
                        "source_label": str(
                            metadata.get("source_label") or jsonl_path.name
                        ),
                    }
                )
                documents.append(Document(page_content=text, metadata=metadata))
        if documents:
            corpus[collection_path.name] = documents
    return corpus


def _metadata_alias_values(metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw_aliases = metadata.get("aliases")
    if isinstance(raw_aliases, (list, tuple, set)):
        for value in raw_aliases:
            if isinstance(value, dict):
                value = value.get("display") or value.get("alias_display")
            if value:
                values.append(str(value).strip())
    for key in ("disease", "heading", "canonical_name"):
        value = str(metadata.get(key) or "").strip()
        if value:
            values.append(value)
    return values


def build_term_catalog(
    corpus: dict[str, list[Document]],
) -> list[dict[str, Any]]:
    """문서 집합에서 표준용어·alias 레코드를 생성한다.

    ``canonical_name``과 동일한 표현은 높은 우선순위를 갖고, metadata의
    alias와 본문의 관련어는 낮은 우선순위를 갖는다. 같은 표현이 다른 항목의
    표준명으로도 존재하면 표준명 소유 항목에만 남겨 중복 alias로 인한
    초성 검색 충돌을 줄인다.
    """
    terms: dict[str, dict[str, Any]] = {}

    for collection, documents in corpus.items():
        for document in documents:
            metadata = document.metadata
            canonical_name = _canonical_name(metadata)
            canonical_key = str(
                metadata.get("canonical_key") or canonical_name
            ).strip()
            if not canonical_name or not canonical_key:
                continue

            entry = terms.setdefault(
                canonical_key,
                {
                    "canonical_key": canonical_key,
                    "canonical_name": canonical_name,
                    "term_type": _term_type(collection, metadata),
                    "_aliases": {},
                },
            )
            aliases: dict[str, dict[str, Any]] = entry["_aliases"]
            _add_alias(aliases, canonical_name, priority=100, alias_type="CANONICAL")

            for value in _iter_metadata_aliases(metadata):
                _add_alias(aliases, value, priority=60, alias_type="SYNONYM")

            for related_line in RELATED_TERMS_PATTERN.findall(document.page_content):
                for value in re.split(r"[,，、;/|]", related_line):
                    _add_alias(aliases, value, priority=30, alias_type="USER_ALIAS")

    _remove_aliases_owned_by_another_canonical(terms)
    return [_finalize_term(entry) for entry in terms.values()]


def _canonical_name(metadata: dict[str, Any]) -> str:
    """metadata에서 사람이 읽을 수 있는 표준명을 고른다."""
    return str(
        metadata.get("disease")
        or metadata.get("heading")
        or metadata.get("canonical_name")
        or metadata.get("canonical_key")
        or ""
    ).strip()


def _term_type(collection: str, metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("term_type") or "").strip().upper()
    if explicit:
        return explicit
    category = str(metadata.get("category") or "").casefold()
    if "medication" in collection.casefold():
        return "MEDICATION"
    if "health_checkup" in collection.casefold():
        return "SCREENING"
    if category == "symptom":
        return "SYMPTOM"
    return "DISEASE"


def _iter_metadata_aliases(metadata: dict[str, Any]) -> Iterable[str]:
    values = metadata.get("aliases")
    if isinstance(values, (list, tuple, set)):
        for value in values:
            if isinstance(value, dict):
                value = value.get("display") or value.get("alias_display")
            if value:
                yield str(value).strip()
    for key in ("disease", "heading"):
        value = str(metadata.get(key) or "").strip()
        if value:
            yield value


def _add_alias(
    aliases: dict[str, dict[str, Any]],
    display: str,
    *,
    priority: int,
    alias_type: str,
) -> None:
    display = str(display or "").strip()
    normalized = normalize_search_text(display)
    if len(normalized) < 2:
        return
    current = aliases.get(normalized)
    if current is None or priority > int(current["priority"]):
        aliases[normalized] = {
            "display": display,
            "alias_type": alias_type,
            "priority": priority,
        }


def _remove_aliases_owned_by_another_canonical(
    terms: dict[str, dict[str, Any]],
) -> None:
    owners: dict[str, set[str]] = {}
    for key, entry in terms.items():
        canonical_key = normalize_search_text(entry["canonical_name"])
        if canonical_key:
            owners.setdefault(canonical_key, set()).add(key)

    for key, entry in terms.items():
        canonical_normalized = normalize_search_text(entry["canonical_name"])
        aliases: dict[str, dict[str, Any]] = entry["_aliases"]
        for alias_key in list(aliases):
            owner_keys = owners.get(alias_key, set())
            if owner_keys and key not in owner_keys and len(owner_keys) == 1:
                del aliases[alias_key]
        aliases.setdefault(
            canonical_normalized,
            {
                "display": entry["canonical_name"],
                "alias_type": "CANONICAL",
                "priority": 100,
            },
        )


def _finalize_term(entry: dict[str, Any]) -> dict[str, Any]:
    aliases = sorted(
        entry.pop("_aliases", {}).values(),
        key=lambda value: (-int(value["priority"]), value["display"]),
    )
    return {
        **entry,
        "aliases": aliases,
    }
