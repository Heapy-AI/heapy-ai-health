#!/usr/bin/env python3
"""골든데이터셋으로 Pinecone Retrieval 성능을 평가한다.

작성자: 김진우

보정용 데이터 실행 예시:
    python -m evaluation.retrieval_evaluator --split calibration
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import (
    EMBED_MODEL,
    PINECONE_INDEX_NAME,
    SEARCH_COLLECTIONS,
)
from app.services.search_result_merger import merge_search_results
from app.services.vector_search import PineconeSearchService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD_PATTERN = "RAG_골든데이터셋_*_2290.jsonl"
DOMAIN_COLLECTIONS = {
    "disease": "disease_info",
    "medication": "medication_info",
    "health_screening": "health_checkup_info",
}
METRIC_K_VALUES = (1, 3, 5)
MRR_K = 10


@dataclass(frozen=True)
class RetrievalMetrics:
    """단일 질문의 Retrieval 지표."""

    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr_at_10: float


def normalize_document_id(domain: str, document_id: str) -> str:
    """골든 문서 ID를 Pinecone record ID 표현으로 정규화한다."""
    normalized = str(document_id).strip()
    if domain == "health_screening" and normalized.startswith("screening:"):
        parts = normalized.split(":")
        if len(parts) >= 2 and parts[1]:
            return parts[1].upper()
    return normalized


def calculate_retrieval_metrics(
    retrieved_ids: Sequence[str],
    gold_ids: Iterable[str],
    acceptable_ids: Iterable[str],
) -> RetrievalMetrics:
    """검색 순위 한 건에서 Hit·Recall·MRR을 계산한다."""
    ranked = list(dict.fromkeys(str(value) for value in retrieved_ids))
    gold = {str(value) for value in gold_ids}
    acceptable = {str(value) for value in acceptable_ids}
    if not gold:
        raise ValueError("답변 가능 문항은 gold_ids가 비어 있을 수 없습니다.")
    if not acceptable:
        raise ValueError("답변 가능 문항은 acceptable_ids가 비어 있을 수 없습니다.")

    hits = {
        k: float(any(record_id in acceptable for record_id in ranked[:k]))
        for k in METRIC_K_VALUES
    }
    recalls = {
        k: len(gold.intersection(ranked[:k])) / len(gold)
        for k in METRIC_K_VALUES
    }
    reciprocal_rank = 0.0
    for rank, record_id in enumerate(ranked[:MRR_K], start=1):
        if record_id in acceptable:
            reciprocal_rank = 1.0 / rank
            break

    return RetrievalMetrics(
        hit_at_1=hits[1],
        hit_at_3=hits[3],
        hit_at_5=hits[5],
        recall_at_1=recalls[1],
        recall_at_3=recalls[3],
        recall_at_5=recalls[5],
        mrr_at_10=reciprocal_rank,
    )


def _find_gold_path(explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        path = explicit_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"골든데이터셋을 찾을 수 없습니다: {path}")
        return path

    matches = sorted((ROOT / "data").glob(DEFAULT_GOLD_PATTERN))
    if len(matches) != 1:
        raise RuntimeError(
            "골든데이터셋 JSONL은 정확히 하나여야 합니다: "
            f"pattern={DEFAULT_GOLD_PATTERN}, count={len(matches)}"
        )
    return matches[0]


def load_gold_rows(path: Path, split: str) -> list[dict[str, Any]]:
    """요청한 평가 구간의 골든 문항을 로드하고 필수 필드를 검증한다."""
    rows: list[dict[str, Any]] = []
    seen_question_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("split") != split:
                continue
            question_id = str(row.get("question_id", "")).strip()
            question = str(row.get("question", "")).strip()
            domain = str(row.get("domain", "")).strip()
            if not question_id or not question or domain not in DOMAIN_COLLECTIONS:
                raise ValueError(
                    f"골든 필수 필드가 올바르지 않습니다: {path.name}:{line_number}"
                )
            if question_id in seen_question_ids:
                raise ValueError(f"중복 question_id입니다: {question_id}")
            seen_question_ids.add(question_id)
            rows.append(row)
    if not rows:
        raise RuntimeError(f"평가할 문항이 없습니다: split={split}")
    return rows


def _document_payload(document) -> dict[str, Any]:
    return {
        "record_id": str(document.metadata.get("record_id", "")),
        "collection": str(document.metadata.get("collection", "")),
        "score": float(document.metadata.get("score", 0.0) or 0.0),
        "source": str(document.metadata.get("source", "")),
    }


def _normalized_gold_ids(row: Mapping[str, Any], key: str) -> list[str]:
    domain = str(row["domain"])
    return [normalize_document_id(domain, value) for value in row.get(key, [])]


def _mean_metrics(rows: Sequence[Mapping[str, Any]], result_key: str) -> dict[str, float]:
    metric_rows = [row[result_key]["metrics"] for row in rows if row.get("answerable")]
    if not metric_rows:
        return {}
    return {
        key: statistics.fmean(float(metrics[key]) for metrics in metric_rows)
        for key in metric_rows[0]
    }


def _group_metrics(
    rows: Sequence[Mapping[str, Any]],
    result_key: str,
    group_key: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[group_key])].append(row)
    return {
        group: {
            "total": len(items),
            "answerable": sum(bool(item["answerable"]) for item in items),
            "metrics": _mean_metrics(items, result_key),
        }
        for group, items in sorted(grouped.items())
    }


def _score_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    groups = {
        "answerable": [row for row in rows if row["answerable"]],
        "unanswerable": [row for row in rows if not row["answerable"]],
    }
    summary: dict[str, dict[str, float]] = {}
    for name, items in groups.items():
        scores = [
            float(item["combined"]["documents"][0]["score"])
            for item in items
            if item["combined"]["documents"]
        ]
        if scores:
            summary[name] = {
                "count": float(len(scores)),
                "min": min(scores),
                "mean": statistics.fmean(scores),
                "median": statistics.median(scores),
                "max": max(scores),
            }
    return summary


def build_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """전체·분야·유형·난이도별 Retrieval 요약을 만든다."""
    return {
        "total": len(rows),
        "answerable": sum(bool(row["answerable"]) for row in rows),
        "unanswerable": sum(not bool(row["answerable"]) for row in rows),
        "oracle": {
            "overall": _mean_metrics(rows, "oracle"),
            "by_domain": _group_metrics(rows, "oracle", "domain"),
            "by_question_type": _group_metrics(rows, "oracle", "question_type"),
            "by_difficulty": _group_metrics(rows, "oracle", "difficulty"),
        },
        "combined": {
            "overall": _mean_metrics(rows, "combined"),
            "by_domain": _group_metrics(rows, "combined", "domain"),
            "by_question_type": _group_metrics(
                rows,
                "combined",
                "question_type",
            ),
            "by_difficulty": _group_metrics(rows, "combined", "difficulty"),
        },
        "combined_top_score": _score_summary(rows),
    }


def _empty_metrics() -> dict[str, float] | None:
    return None


def evaluate(
    rows: Sequence[Mapping[str, Any]],
    *,
    candidate_k: int,
    final_k: int,
    max_per_collection: int,
    min_score: float,
) -> list[dict[str, Any]]:
    """골든 질문을 Oracle·Combined 두 경로로 검색해 문항별 결과를 만든다."""
    service = PineconeSearchService()
    questions = [str(row["question"]) for row in rows]
    print(f"질문 {len(questions)}건 일괄 임베딩 중...", flush=True)
    vectors = service._embeddings.embed_documents(questions)
    results: list[dict[str, Any]] = []

    for index, (row, query_vector) in enumerate(zip(rows, vectors, strict=True), start=1):
        started_at = time.perf_counter()
        domain = str(row["domain"])
        oracle_collection = DOMAIN_COLLECTIONS[domain]
        query_k = max(candidate_k, MRR_K)
        combined_search = service.search_many_by_vector(
            list(SEARCH_COLLECTIONS),
            query_vector,
            query_k,
        )
        oracle_documents = sorted(
            (
                document
                for document in combined_search.documents
                if document.metadata.get("collection") == oracle_collection
            ),
            key=lambda document: -float(
                document.metadata.get("score", 0.0) or 0.0
            ),
        )[:query_k]
        combined_documents = merge_search_results(
            combined_search.documents,
            final_top_k=final_k,
            max_per_collection=max_per_collection,
            min_score=min_score,
        )

        answerable = bool(row["answerable"])
        gold_ids = _normalized_gold_ids(row, "gold_document_ids")
        acceptable_ids = _normalized_gold_ids(row, "acceptable_document_ids")
        oracle_ids = [str(doc.metadata.get("record_id", "")) for doc in oracle_documents]
        combined_ids = [
            str(doc.metadata.get("record_id", "")) for doc in combined_documents
        ]
        oracle_metrics = (
            asdict(calculate_retrieval_metrics(oracle_ids, gold_ids, acceptable_ids))
            if answerable
            else _empty_metrics()
        )
        combined_metrics = (
            asdict(calculate_retrieval_metrics(combined_ids, gold_ids, acceptable_ids))
            if answerable
            else _empty_metrics()
        )
        results.append(
            {
                "question_id": row["question_id"],
                "split": row["split"],
                "domain": domain,
                "question_type": row["question_type"],
                "difficulty": row["difficulty"],
                "answerable": answerable,
                "expected_behavior": row["expected_behavior"],
                "question": row["question"],
                "gold_document_ids": gold_ids,
                "acceptable_document_ids": acceptable_ids,
                "oracle": {
                    "collection": oracle_collection,
                    "documents": [_document_payload(doc) for doc in oracle_documents],
                    "metrics": oracle_metrics,
                },
                "combined": {
                    "documents": [_document_payload(doc) for doc in combined_documents],
                    "metrics": combined_metrics,
                    "failed_collections": sorted(combined_search.errors),
                },
                "latency_ms": (time.perf_counter() - started_at) * 1000,
            }
        )
        if index % 10 == 0 or index == len(rows):
            print(f"검색 완료 {index}/{len(rows)}", flush=True)
    return results


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_results(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Path:
    """실험 설정·문항별 결과·요약 지표를 한 실행 폴더에 저장한다."""
    run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / run_name
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "config.json", config)
    with (output_dir / "per_question_results.jsonl").open(
        "w",
        encoding="utf-8",
    ) as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    _write_json(output_dir / "retrieval_metrics.json", build_summary(rows))
    return output_dir


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("0 이상의 유한한 실수여야 합니다.")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("1 이상의 정수여야 합니다.")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-path", type=Path)
    parser.add_argument(
        "--split",
        choices=("calibration", "test"),
        default="calibration",
    )
    parser.add_argument("--candidate-k", type=_positive_int, default=10)
    parser.add_argument("--final-k", type=_positive_int, default=10)
    parser.add_argument("--max-per-collection", type=_positive_int, default=10)
    parser.add_argument("--min-score", type=_non_negative_float, default=0.0)
    parser.add_argument("--limit", type=_positive_int)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "evaluation" / "results" / "retrieval",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.final_k > args.candidate_k * len(SEARCH_COLLECTIONS):
        raise ValueError("final-k가 전체 후보 수보다 클 수 없습니다.")
    gold_path = _find_gold_path(args.gold_path)
    gold_rows = load_gold_rows(gold_path, args.split)
    if args.limit is not None:
        gold_rows = gold_rows[: args.limit]

    config = {
        "gold_path": str(gold_path),
        "split": args.split,
        "question_count": len(gold_rows),
        "index_name": PINECONE_INDEX_NAME,
        "embedding_model": EMBED_MODEL,
        "search_collections": list(SEARCH_COLLECTIONS),
        "candidate_k": args.candidate_k,
        "final_k": args.final_k,
        "max_per_collection": args.max_per_collection,
        "min_score": args.min_score,
    }
    results = evaluate(
        gold_rows,
        candidate_k=args.candidate_k,
        final_k=args.final_k,
        max_per_collection=args.max_per_collection,
        min_score=args.min_score,
    )
    output_dir = save_results(args.output_root, results, config)
    print(f"평가 결과 저장 완료: {output_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
