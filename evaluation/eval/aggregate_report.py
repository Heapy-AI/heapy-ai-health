"""평가 원시 결과를 집계해 metrics_summary.json · per_question.csv · report.md를 만든다.

실행 예:
    PYTHONPATH=. python evaluation/eval/aggregate_report.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.eval.metrics import deterministic_metrics, mean, percentile  # noqa: E402

RAGAS_LABELS = {
    "faithfulness": "근거충실도 (ragas faithfulness)",
    "answer_correctness": "정답일치율 (ragas answer_correctness)",
    "context_recall": "근거재현율 (ragas context_recall)",
    "llm_context_precision_with_reference": "근거정밀도 (ragas context_precision)",
}

STAGE_LABELS = [
    ("embed_ms", "질문 임베딩"),
    ("intent_ms", "Intent 분류"),
    ("search_ms", "Pinecone 검색(3 namespace 병렬)"),
    ("plan_ms", "근거계획 생성 (LLM)"),
    ("generate_ttfb_ms", "답변 생성 TTFB (LLM)"),
    ("generate_total_ms", "답변 생성 완료 (LLM)"),
    ("audit_ms", "사후 감사 (LLM)"),
    ("first_token_ms", "종단 TTFB (요청→첫 토큰)"),
    ("end_to_end_ms", "종단 총 지연 (요청→감사 완료)"),
]


def _fmt(value, digits: int = 4, percent: bool = False) -> str:
    """None/NaN을 안전하게 표시한다."""
    if value is None or (isinstance(value, float) and value != value):
        return "N/A"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.{digits}f}"


def _fmt_ms(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "N/A"
    return f"{value:,.0f}"


def _metric_values(records: list[dict], key: str) -> list[float]:
    values = []
    for record in records:
        value = record.get("metrics", {}).get(key)
        if value is None:
            continue
        if isinstance(value, float) and value != value:
            continue
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _timing_values(records: list[dict], key: str) -> list[float]:
    return [
        float(record["timings"][key])
        for record in records
        if record.get("timings", {}).get(key) is not None
    ]


def _stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": mean(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "max": max(values) if values else float("nan"),
    }


def _gold_collection(document_id: str) -> str:
    """정답 문서 ID로부터 소속 namespace를 추론한다."""
    if document_id.startswith("kdca-"):
        return "disease_info"
    if document_id.startswith("eyak:"):
        return "medication_info"
    return "health_checkup_info"


def build_diagnostics(ok: list[dict]) -> dict:
    """성능 저하 원인을 분리하기 위한 진단 수치를 계산한다."""
    from evaluation.eval.metrics import document_group, is_abstention, normalize_ids

    plan_rejected = [r for r in ok if r["verification_method"] == "plan_rejected"]
    rejected_with_gold = 0
    for record in plan_rejected:
        relevant = set(
            normalize_ids(
                record["gold"].get("acceptable_document_ids")
                or record["gold"].get("gold_document_ids")
                or []
            )
        )
        final_ids = set(normalize_ids(d["record_id"] for d in record["retrieved_documents"]))
        if relevant & final_ids:
            rejected_with_gold += 1

    answerable = [r for r in ok if r["gold"]["answerable"]]
    false_abstention = [
        r for r in answerable if is_abstention(r["answer"], r["grounded"])
    ]
    misrouted = [
        r for r in answerable if r["intent"] in ("ignore", "general_chat")
    ]

    # 정답 문서가 속한 namespace 외의 청크가 문맥을 차지한 비율
    off_domain_total = 0
    context_total = 0
    for record in ok:
        gold_ids = record["gold"].get("gold_document_ids") or []
        if not gold_ids or not record["retrieved_documents"]:
            continue
        target = _gold_collection(gold_ids[0])
        for document in record["retrieved_documents"]:
            context_total += 1
            if document["collection"] != target:
                off_domain_total += 1

    # 같은 원천 문서의 다른 섹션만 회수한 경우(청크 경계 실패)
    section_only = 0
    scored = 0
    for record in ok:
        relevant = set(
            normalize_ids(
                record["gold"].get("acceptable_document_ids")
                or record["gold"].get("gold_document_ids")
                or []
            )
        )
        if not relevant or not record["retrieved_documents"]:
            continue
        scored += 1
        final_ids = normalize_ids(d["record_id"] for d in record["retrieved_documents"])
        if set(final_ids) & relevant:
            continue
        if {document_group(d) for d in final_ids} & {document_group(d) for d in relevant}:
            section_only += 1

    return {
        "plan_rejected_total": len(plan_rejected),
        "plan_rejected_with_gold_in_context": rejected_with_gold,
        "plan_rejected_without_gold_in_context": len(plan_rejected) - rejected_with_gold,
        "false_abstention_count": len(false_abstention),
        "false_abstention_rate": (
            len(false_abstention) / len(answerable) if answerable else float("nan")
        ),
        "intent_misrouted_count": len(misrouted),
        "intent_misrouted_rate": len(misrouted) / len(answerable) if answerable else float("nan"),
        "intent_misrouted_mean_confidence": mean([r["intent_confidence"] for r in misrouted]),
        "off_domain_context_share": (
            off_domain_total / context_total if context_total else float("nan")
        ),
        "section_mismatch_count": section_only,
        "section_mismatch_rate": section_only / scored if scored else float("nan"),
        "section_mismatch_denominator": scored,
    }


def build_summary(records: list[dict], ragas_scores: dict[str, dict]) -> dict:
    """전체·그룹별 지표를 계산한다."""
    ok = [r for r in records if r.get("status") == "ok"]
    errors = [r for r in records if r.get("status") != "ok"]
    answerable = [r for r in ok if r["gold"]["answerable"]]
    unanswerable = [r for r in ok if not r["gold"]["answerable"]]
    rag_routed = [r for r in ok if r["intent"] in ("simple_lookup", "comprehensive")]

    deterministic_keys = [
        "hit@1", "hit@3", "hit@5", "mrr@10", "ndcg@10", "map",
        "context_recall_id", "context_precision_id",
        "candidate_hit@1", "candidate_hit@3", "candidate_hit@5",
        "candidate_mrr@10", "candidate_context_recall_id",
        "group_hit@1", "group_hit@3", "group_hit@5", "candidate_group_hit@3",
        "citation_accuracy", "citation_hit", "source_uri_match",
        "answer_char_f1", "answer_token_f1", "answer_semantic_similarity",
        "reference_coverage", "abstention_correct", "is_abstention",
    ]

    def deterministic_block(subset: list[dict]) -> dict:
        return {key: mean(_metric_values(subset, key)) for key in deterministic_keys}

    def ragas_block(subset: list[dict]) -> dict:
        block = {}
        for column in RAGAS_LABELS:
            values = [
                ragas_scores[r["question_id"]][column]
                for r in subset
                if r["question_id"] in ragas_scores
                and ragas_scores[r["question_id"]].get(column) is not None
            ]
            block[column] = mean(values) if values else float("nan")
            block[f"{column}__n"] = len(values)
        return block

    groups: dict[str, dict] = {}
    for group_name, key_function in (
        ("domain", lambda r: r["gold"]["domain"]),
        ("difficulty", lambda r: r["gold"]["difficulty"]),
        ("split", lambda r: r["gold"]["split"]),
        ("intent", lambda r: r["intent"]),
        ("answerable", lambda r: "answerable" if r["gold"]["answerable"] else "unanswerable"),
        ("question_type", lambda r: r["gold"]["question_type"]),
    ):
        buckets: dict[str, list[dict]] = defaultdict(list)
        for record in ok:
            buckets[key_function(record)].append(record)
        groups[group_name] = {
            name: {
                "n": len(subset),
                **deterministic_block(subset),
                **ragas_block(subset),
                "first_token_ms_p50": percentile(_timing_values(subset, "first_token_ms"), 0.5),
                "end_to_end_ms_p50": percentile(_timing_values(subset, "end_to_end_ms"), 0.5),
            }
            for name, subset in sorted(buckets.items(), key=lambda pair: -len(pair[1]))
        }

    collection_hits = Counter()
    collection_top1 = Counter()
    for record in ok:
        for document in record["retrieved_documents"]:
            collection_hits[document["collection"]] += 1
        if record["retrieved_documents"]:
            collection_top1[record["retrieved_documents"][0]["collection"]] += 1

    diagnostics = build_diagnostics(ok)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "total": len(records),
            "ok": len(ok),
            "errors": len(errors),
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "rag_routed": len(rag_routed),
            "ragas_scored": len([r for r in ok if r["question_id"] in ragas_scores]),
        },
        "overall": {
            **deterministic_block(ok),
            **ragas_block(ok),
        },
        "answerable_only": {
            **deterministic_block(answerable),
            **ragas_block(answerable),
        },
        "unanswerable_only": deterministic_block(unanswerable),
        "intent": {
            "distribution": dict(Counter(r["intent"] for r in ok)),
            "source_distribution": dict(Counter(r["intent_source"] for r in ok)),
            "mean_confidence": mean([r["intent_confidence"] for r in ok]),
            "p05_confidence": percentile([r["intent_confidence"] for r in ok], 0.05),
            "uncertain_rate": mean([1.0 if r["intent_uncertain"] else 0.0 for r in ok]),
            "guard_triggered_rate": mean([1.0 if r["guard_triggered"] else 0.0 for r in ok]),
            "rag_routing_rate": len(rag_routed) / len(ok) if ok else float("nan"),
            "guard_reasons": dict(Counter(r["guard_reason"] for r in ok if r["guard_reason"])),
        },
        "grounding": {
            "grounded_rate": mean([1.0 if r["grounded"] else 0.0 for r in ok]),
            "audit_status": dict(Counter(r["audit_status"] for r in ok)),
            "verification_method": dict(Counter(r["verification_method"] for r in ok)),
            "audit_pass_rate": mean(
                [1.0 if r["audit_status"] == "passed" else 0.0 for r in ok if r["audit_status"] in ("passed", "failed")]
            ),
            "unsupported_claim_rate": mean([1.0 if r["unsupported_claims"] else 0.0 for r in ok]),
            "plan_rejected_rate": mean(
                [1.0 if r["verification_method"] == "plan_rejected" else 0.0 for r in ok]
            ),
            "mean_cited_chunks": mean([float(len(r["cited_chunk_ids"])) for r in ok]),
        },
        "retrieval_scores": {
            "top1_score_mean": mean([r["top_score"] for r in ok if r["top_score"] is not None]),
            "top1_score_p50": percentile([r["top_score"] for r in ok if r["top_score"] is not None], 0.5),
            "mean_score_mean": mean([r["mean_score"] for r in ok if r["mean_score"] is not None]),
            "documents_per_question": mean([float(len(r["retrieved_documents"])) for r in ok]),
            "collection_share": dict(collection_hits),
            "collection_top1": dict(collection_top1),
            "empty_retrieval": sum(1 for r in ok if not r["retrieved_documents"]),
            "failed_collections": dict(
                Counter(c for r in ok for c in r["failed_collections"])
            ),
        },
        "diagnostics": diagnostics,
        "latency_ms": {key: _stats(_timing_values(ok, key)) for key, _ in STAGE_LABELS},
        "answer_length": _stats([float(r["answer_length"]) for r in ok]),
        "groups": groups,
        "errors": [
            {"question_id": r["question_id"], "error": r.get("error", "")} for r in errors
        ],
    }


def write_csv(records: list[dict], ragas_scores: dict[str, dict], path: Path) -> None:
    """스프레드시트 검토용 1행 1질문 요약을 저장한다."""
    columns = [
        "question_id", "domain", "split", "difficulty", "question_type", "answerable",
        "question", "intent", "intent_confidence", "intent_uncertain", "guard_triggered",
        "grounded", "audit_status", "verification_method",
        "gold_document_ids", "retrieved_document_ids", "cited_record_ids",
        "top_score", "hit@1", "hit@3", "hit@5", "mrr@10",
        "context_recall_id", "context_precision_id", "citation_accuracy", "source_uri_match",
        "answer_char_f1", "answer_semantic_similarity", "abstention_correct",
        "faithfulness", "answer_correctness", "context_recall",
        "llm_context_precision_with_reference",
        "embed_ms", "intent_ms", "search_ms", "plan_ms",
        "generate_ttfb_ms", "audit_ms", "first_token_ms", "end_to_end_ms",
        "answer_length", "reference_answer", "answer",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            if record.get("status") != "ok":
                writer.writerow({
                    "question_id": record["question_id"],
                    "question": record.get("question", ""),
                    "intent": "ERROR",
                    "answer": record.get("error", ""),
                })
                continue
            metrics = record["metrics"]
            ragas = ragas_scores.get(record["question_id"], {})
            row = {
                "question_id": record["question_id"],
                "domain": record["gold"]["domain"],
                "split": record["gold"]["split"],
                "difficulty": record["gold"]["difficulty"],
                "question_type": record["gold"]["question_type"],
                "answerable": record["gold"]["answerable"],
                "question": record["question"],
                "intent": record["intent"],
                "intent_confidence": round(record["intent_confidence"], 4),
                "intent_uncertain": record["intent_uncertain"],
                "guard_triggered": record["guard_triggered"],
                "grounded": record["grounded"],
                "audit_status": record["audit_status"],
                "verification_method": record["verification_method"],
                "gold_document_ids": "|".join(record["gold"]["gold_document_ids"]),
                "retrieved_document_ids": "|".join(
                    doc["record_id"] for doc in record["retrieved_documents"]
                ),
                "cited_record_ids": "|".join(metrics.get("resolved_cited_record_ids") or []),
                "top_score": record["top_score"],
                "answer_length": record["answer_length"],
                "reference_answer": record["gold"]["reference_answer"],
                "answer": record["answer"],
            }
            for key in (
                "hit@1", "hit@3", "hit@5", "mrr@10", "context_recall_id",
                "context_precision_id", "citation_accuracy", "source_uri_match",
                "answer_char_f1", "answer_semantic_similarity", "abstention_correct",
            ):
                row[key] = metrics.get(key)
            for key in RAGAS_LABELS:
                row[key] = ragas.get(key)
            for key in (
                "embed_ms", "intent_ms", "search_ms", "plan_ms",
                "generate_ttfb_ms", "audit_ms", "first_token_ms", "end_to_end_ms",
            ):
                value = record["timings"].get(key)
                row[key] = round(value, 1) if isinstance(value, (int, float)) else None
            writer.writerow(row)


def _group_table(groups: dict, keys: list[tuple[str, str]], header: str) -> list[str]:
    lines = [f"| {header} | 건수 | " + " | ".join(label for _, label in keys) + " |"]
    lines.append("|---|---:|" + "---:|" * len(keys))
    for name, stats in groups.items():
        cells = []
        for key, _ in keys:
            value = stats.get(key)
            if key.endswith("_ms_p50"):
                cells.append(_fmt_ms(value))
            else:
                cells.append(
                    _fmt(value, 3, percent=key.startswith(("hit", "abstention", "citation_hit")))
                )
        lines.append(f"| {name} | {stats['n']} | " + " | ".join(cells) + " |")
