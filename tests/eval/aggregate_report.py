"""평가 원시 결과를 집계해 metrics_summary.json · per_question.csv · report.md를 만든다.

실행 예:
    PYTHONPATH=. python tests/eval/aggregate_report.py
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

from tests.eval.metrics import deterministic_metrics, mean, percentile  # noqa: E402

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
    from tests.eval.metrics import document_group, is_abstention, normalize_ids

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
    answered = [r for r in ok if not r["metrics"]["is_abstention"]]

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
        (
            "response_type",
            lambda r: "abstained" if r["metrics"]["is_abstention"] else "answered",
        ),
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
            "answered": len(answered),
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
        "answered_only": {
            **deterministic_block(answered),
            **ragas_block(answered),
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
    return lines


def build_report(meta: dict, summary: dict, ragas_summary: dict | None) -> str:
    """report.md 본문을 만든다."""
    overall = summary["overall"]
    answerable = summary["answerable_only"]
    latency = summary["latency_ms"]
    counts = summary["counts"]
    system = meta.get("system", {})

    lines: list[str] = []
    add = lines.append

    add("# HEAPY 건강정보 RAG — 골든 데이터셋 성능 평가 리포트")
    add("")
    add(f"- 생성 시각: `{summary['generated_at']}`")
    add(f"- 데이터셋: `{meta.get('dataset')}` (전체 {meta.get('dataset_total'):,}건)")
    add(
        f"- 평가 표본: **{counts['total']}건** "
        f"(층화표본, seed={meta.get('seed')}) · 성공 {counts['ok']}건 / 오류 {counts['errors']}건"
    )
    add(f"- 답변가능 {counts['answerable']}건 · 답변불가(거절 기대) {counts['unanswerable']}건")
    add(
        f"- 실행: 워커 {meta.get('workers')}개 · 벽시계 {meta.get('wall_seconds')}s "
        f"· 처리량 {meta.get('questions_per_second')} q/s (준비 {meta.get('setup_seconds')}s 별도)"
    )
    add("")
    add("## 1. 평가 대상 시스템")
    add("")
    add("| 구성요소 | 값 |")
    add("|---|---|")
    add(f"| 답변 LLM | `{system.get('llm_model')}` (temperature=0) |")
    add(f"| 임베딩 모델 | `{system.get('embed_model')}` (768차원) |")
    add(f"| 벡터DB | Pinecone `heapy-rag` · namespace {system.get('search_collections')} |")
    add(f"| namespace별 top-k | {system.get('top_k_per_collection')} |")
    add(f"| 최종 문맥 청크 수 | {system.get('final_top_k')} (컬렉션당 최대 {system.get('max_per_collection')}) |")
    add(f"| 최소 유사도 컷 | {system.get('min_score')} |")
    add(f"| Intent 모델 | `{system.get('intent_model_version')}` (최소신뢰도 {system.get('intent_min_confidence')}) |")
    add(
        "| 응답 경로 | Safety Guard → Intent 분류 → 다중 namespace 검색 → 근거계획 선검증 "
        "→ 답변 스트리밍 → 사후 감사 |"
    )
    add("")
    if ragas_summary:
        add(
            f"> ragas `{ragas_summary.get('ragas_version')}` · 심판 LLM `{ragas_summary.get('judge_llm')}` "
            f"· 채점 {ragas_summary.get('scored')}건 ({ragas_summary.get('elapsed_seconds')}s)"
        )
        add("")

    # ------------------------------------------------------------------
    answered = summary["answered_only"]
    answered_n = summary["counts"]["answered"]
    abstained_n = counts["ok"] - answered_n

    add("## 2. 핵심 성능 요약")
    add("")
    add(
        f"| 지표 | 정의 | 전체 ({counts['ok']}건) | 답변가능 질문 ({counts['answerable']}건) "
        f"| 실제 답변 생성 ({answered_n}건) |"
    )
    add("|---|---|---:|---:|---:|")
    for label, definition, key in (
        (
            "**근거충실도**",
            "답변 주장이 검색 문맥으로 뒷받침되는 비율 (ragas faithfulness)",
            "faithfulness",
        ),
        (
            "**정답일치율**",
            "참조 정답과의 사실·의미 일치도 (ragas answer_correctness)",
            "answer_correctness",
        ),
        (
            "**근거재현율**",
            "정답 문서를 문맥에 회수한 비율 (문서ID 기준)",
            "context_recall_id",
        ),
        (
            "근거재현율 (ragas)",
            "참조 정답 문장이 문맥에서 재구성 가능한 비율",
            "context_recall",
        ),
        (
            "**근거정밀도**",
            "회수 문맥 중 정답 문서 비율 (문서ID 기준)",
            "context_precision_id",
        ),
        (
            "근거정밀도 (ragas)",
            "관련 청크가 상위에 배치된 정도",
            "llm_context_precision_with_reference",
        ),
        (
            "**출처ID일치율**",
            "LLM이 인용한 청크가 정답 문서인 비율",
            "citation_accuracy",
        ),
        (
            "답변–정답 임베딩 유사도",
            "답변과 참조 정답의 코사인 유사도 (ko-sroberta)",
            "answer_semantic_similarity",
        ),
    ):
        add(
            f"| {label} | {definition} | {_fmt(overall.get(key))} "
            f"| {_fmt(answerable.get(key))} | {_fmt(answered.get(key))} |"
        )
    add(
        f"| **TTFB (p50)** | 요청→첫 토큰 지연 "
        f"| {_fmt_ms(latency['first_token_ms']['p50'])} ms | — | — |"
    )
    add(
        f"| TTFB (p95) | 요청→첫 토큰 지연 상위 5% "
        f"| {_fmt_ms(latency['first_token_ms']['p95'])} ms | — | — |"
    )
    add(
        f"| 종단 지연 (p50) | 요청→사후 감사 완료 "
        f"| {_fmt_ms(latency['end_to_end_ms']['p50'])} ms | — | — |"
    )
    add("")
    add(
        f"> **해석 주의** — 전체 평균에는 시스템이 \"지식베이스에 근거 없음\"으로 거절한 "
        f"{abstained_n}건이 포함됩니다. ragas는 이 거절 문구를 문맥으로 뒷받침되지 않는 "
        f"주장으로 채점하므로(근거충실도 "
        f"{_fmt(summary['groups']['response_type'].get('abstained', {}).get('faithfulness'))}), "
        f"전체 평균이 크게 낮아집니다. **실제로 답변을 생성한 {answered_n}건만 보면 "
        f"근거충실도 {_fmt(answered.get('faithfulness'))}** — 즉 답변을 내놓을 때는 "
        f"거의 예외 없이 검색 문맥에 근거합니다. 현재 시스템의 약점은 "
        f"*환각*이 아니라 *과도한 거절*이며, 그 원인은 검색 단계입니다(9장)."
    )
    add("")

    # ------------------------------------------------------------------
    add("## 3. Intent 분류")
    add("")
    intent = summary["intent"]
    add("| 항목 | 값 |")
    add("|---|---|")
    add(f"| 분류 분포 | {intent['distribution']} |")
    add(f"| 분류 경로 | {intent['source_distribution']} |")
    add(f"| 평균 신뢰도 | {_fmt(intent['mean_confidence'])} |")
    add(f"| 하위 5% 신뢰도 | {_fmt(intent['p05_confidence'])} |")
    add(f"| 저신뢰(uncertain) 비율 | {_fmt(intent['uncertain_rate'], percent=True)} |")
    add(f"| RAG 경로 라우팅율 | {_fmt(intent['rag_routing_rate'], percent=True)} |")
    add(f"| Safety Guard 발동율 | {_fmt(intent['guard_triggered_rate'], percent=True)} |")
    if intent["guard_reasons"]:
        add(f"| Guard 사유 | {intent['guard_reasons']} |")
    add("")
    add("> 골든셋에는 intent 정답 라벨이 없어, 건강 질의가 RAG 경로(`simple_lookup`/`comprehensive`)로")
    add("> 라우팅되는 비율을 라우팅 정확도의 대리 지표로 사용했습니다.")
    add("")
    add("### Intent별 품질")
    add("")
    lines.extend(
        _group_table(
            summary["groups"]["intent"],
            [
                ("hit@3", "hit@3"),
                ("context_recall_id", "근거재현율"),
                ("faithfulness", "근거충실도"),
                ("answer_correctness", "정답일치율"),
                ("first_token_ms_p50", "TTFB p50(ms)"),
            ],
            "Intent",
        )
    )
    add("")

    # ------------------------------------------------------------------
    add("## 4. 검색 성능")
    add("")
    retrieval = summary["retrieval_scores"]
    add("### 4.1 최종 문맥 기준 (LLM에 실제 전달된 청크)")
    add("")
    add("| 지표 | 값 |")
    add("|---|---:|")
    for key, label in (
        ("hit@1", "Hit@1"),
        ("hit@3", "Hit@3"),
        ("hit@5", "Hit@5"),
        ("mrr@10", "MRR@10"),
        ("ndcg@10", "nDCG@10"),
        ("map", "MAP"),
        ("context_recall_id", "근거재현율 (문서ID)"),
        ("context_precision_id", "근거정밀도 (문서ID)"),
    ):
        percent = key.startswith("hit")
        add(f"| {label} | {_fmt(overall.get(key), 4, percent=percent)} |")
    add("")
    add("**원천 문서 단위 완화 기준** — 정답 청크와 같은 질병/의약품/검진항목의 다른 섹션을")
    add("회수한 경우도 적중으로 인정합니다. 청크 경계 문제와 의미 검색 실패를 분리해 봅니다.")
    add("")
    add("| 지표 | 정확 청크 기준 | 원천 문서 기준 | 차이 |")
    add("|---|---:|---:|---:|")
    for strict_key, group_key, label in (
        ("hit@1", "group_hit@1", "Hit@1"),
        ("hit@3", "group_hit@3", "Hit@3"),
        ("hit@5", "group_hit@5", "Hit@5"),
    ):
        strict_value = overall.get(strict_key)
        group_value = overall.get(group_key)
        delta = (
            group_value - strict_value
            if isinstance(strict_value, float) and isinstance(group_value, float)
            and strict_value == strict_value and group_value == group_value
            else None
        )
        add(
            f"| {label} | {_fmt(strict_value, 4, percent=True)} | {_fmt(group_value, 4, percent=True)} "
            f"| {('+' + _fmt(delta, 4, percent=True)) if delta is not None else 'N/A'} |"
        )
    add("")
    add("### 4.2 병합 전 후보 기준 (컬렉션 상한 적용 전)")
    add("")
    add("| 지표 | 최종 문맥 | 병합 전 후보 | 차이 |")
    add("|---|---:|---:|---:|")
    for final_key, candidate_key, label in (
        ("hit@1", "candidate_hit@1", "Hit@1"),
        ("hit@3", "candidate_hit@3", "Hit@3"),
        ("hit@5", "candidate_hit@5", "Hit@5"),
        ("mrr@10", "candidate_mrr@10", "MRR@10"),
        ("context_recall_id", "candidate_context_recall_id", "근거재현율"),
    ):
        final_value = overall.get(final_key)
        candidate_value = overall.get(candidate_key)
        delta = (
            candidate_value - final_value
            if isinstance(final_value, float) and isinstance(candidate_value, float)
            and final_value == final_value and candidate_value == candidate_value
            else None
        )
        add(
            f"| {label} | {_fmt(final_value, 4)} | {_fmt(candidate_value, 4)} "
            f"| {('+' if delta and delta > 0 else '') + _fmt(delta, 4) if delta is not None else 'N/A'} |"
        )
    add("")
    add("### 4.3 검색 분포")
    add("")
    add("| 항목 | 값 |")
    add("|---|---|")
    add(f"| 질문당 평균 문맥 청크 | {_fmt(retrieval['documents_per_question'], 2)} |")
    add(f"| 1순위 유사도 평균 / p50 | {_fmt(retrieval['top1_score_mean'], 3)} / {_fmt(retrieval['top1_score_p50'], 3)} |")
    add(f"| 문맥 평균 유사도 | {_fmt(retrieval['mean_score_mean'], 3)} |")
    add(f"| 컬렉션별 문맥 점유 | {retrieval['collection_share']} |")
    add(f"| 1순위 컬렉션 분포 | {retrieval['collection_top1']} |")
    add(f"| 검색 결과 0건 | {retrieval['empty_retrieval']}건 |")
    add(f"| namespace 검색 실패 | {retrieval['failed_collections'] or '없음'} |")
    add("")

    # ------------------------------------------------------------------
    add("## 5. 생성 품질과 근거 검증")
    add("")
    grounding = summary["grounding"]
    add(f"| 항목 | 전체 ({counts['ok']}건) | 실제 답변 생성 ({answered_n}건) |")
    add("|---|---:|---:|")
    for label, key, percent in (
        ("근거충실도 (ragas faithfulness)", "faithfulness", False),
        ("정답일치율 (ragas answer_correctness)", "answer_correctness", False),
        ("답변-정답 임베딩 코사인 유사도", "answer_semantic_similarity", False),
        ("답변-정답 문자 bigram F1", "answer_char_f1", False),
        ("답변-정답 어절 F1", "answer_token_f1", False),
        ("짧은 정답 포함율 (≤40자 참조답)", "reference_coverage", True),
    ):
        add(
            f"| {label} | {_fmt(overall.get(key), percent=percent)} "
            f"| {_fmt(answered.get(key), percent=percent)} |"
        )
    add("")
    add("| 근거 검증 계층 | 값 |")
    add("|---|---:|")
    add(f"| 근거 확보(grounded) 비율 | {_fmt(grounding['grounded_rate'], percent=True)} |")
    add(f"| 시스템 사후감사 통과율 | {_fmt(grounding['audit_pass_rate'], percent=True)} |")
    add(f"| 미근거 주장 검출 비율 | {_fmt(grounding['unsupported_claim_rate'], percent=True)} |")
    add(f"| 근거계획 반려율 (plan_rejected) | {_fmt(grounding['plan_rejected_rate'], percent=True)} |")
    add(f"| 질문당 평균 인용 청크 수 | {_fmt(grounding['mean_cited_chunks'], 2)} |")
    add(f"| 평균 답변 길이 | {_fmt(summary['answer_length']['mean'], 0)}자 |")
    add("")
    add(f"- 감사 상태 분포: `{grounding['audit_status']}`")
    add(f"- 검증 방식 분포: `{grounding['verification_method']}`")
    add("")
    add("### 5.1 거절(abstention) 처리")
    add("")
    add("| 대상 | 건수 | 거절 정확도 | 실제 거절 비율 |")
    add("|---|---:|---:|---:|")
    add(
        f"| 전체 | {counts['ok']} | {_fmt(overall.get('abstention_correct'), percent=True)} "
        f"| {_fmt(overall.get('is_abstention'), percent=True)} |"
    )
    add(
        f"| 답변가능 (거절하면 오답) | {counts['answerable']} "
        f"| {_fmt(answerable.get('abstention_correct'), percent=True)} "
        f"| {_fmt(answerable.get('is_abstention'), percent=True)} |"
    )
    unanswerable = summary["unanswerable_only"]
    add(
        f"| 답변불가 (거절해야 정답) | {counts['unanswerable']} "
        f"| {_fmt(unanswerable.get('abstention_correct'), percent=True)} "
        f"| {_fmt(unanswerable.get('is_abstention'), percent=True)} |"
    )
    add("")

    # ------------------------------------------------------------------
    add("## 6. 출처·인용 정확도")
    add("")
    add("| 지표 | 값 |")
    add("|---|---:|")
    add(f"| 출처ID일치율 (인용 청크 중 정답 문서) | {_fmt(overall.get('citation_accuracy'))} |")
    add(f"| 인용 적중률 (정답 문서를 1개 이상 인용) | {_fmt(overall.get('citation_hit'), percent=True)} |")
    add(f"| 출처 URI 일치율 | {_fmt(overall.get('source_uri_match'), percent=True)} |")
    add("")

    # ------------------------------------------------------------------
    add("## 7. 처리 속도")
    add("")
    add(f"> 워커 {meta.get('workers')}개 동시 실행 기준입니다. 단계 시간은 각 질문 내부에서 순차 측정됩니다.")
    add("")
    add("| 단계 | 평균 | p50 | p90 | p95 | 최대 | n |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for key, label in STAGE_LABELS:
        stats = latency[key]
        add(
            f"| {label} | {_fmt_ms(stats['mean'])} | {_fmt_ms(stats['p50'])} | {_fmt_ms(stats['p90'])} "
            f"| {_fmt_ms(stats['p95'])} | {_fmt_ms(stats['max'])} | {stats['n']} |"
        )
    add("")
    add("단위: 밀리초(ms)")
    add("")

    # ------------------------------------------------------------------
    add("## 8. 세그먼트별 성능")
    add("")
    quality_columns = [
        ("hit@3", "hit@3"),
        ("context_recall_id", "근거재현율"),
        ("context_precision_id", "근거정밀도"),
        ("citation_accuracy", "출처ID일치율"),
        ("faithfulness", "근거충실도"),
        ("answer_correctness", "정답일치율"),
        ("first_token_ms_p50", "TTFB p50(ms)"),
    ]
    for group_name, header in (
        ("domain", "도메인"),
        ("difficulty", "난이도"),
        ("split", "Split"),
        ("answerable", "답변가능 여부"),
    ):
        add(f"### 8.{('domain', 'difficulty', 'split', 'answerable').index(group_name) + 1} {header}별")
        add("")
        lines.extend(_group_table(summary["groups"][group_name], quality_columns, header))
        add("")

    add("### 8.5 응답 유형별 (답변 생성 vs 거절)")
    add("")
    lines.extend(
        _group_table(summary["groups"]["response_type"], quality_columns, "응답 유형")
    )
    add("")
    add("> `abstained`의 근거충실도·정답일치율이 0에 가까운 것은 품질 문제가 아니라")
    add("> ragas가 \"지식베이스에 근거 없음\"이라는 거절 문구를 채점한 결과입니다.")
    add("> 이 행은 **거절이 얼마나 자주 발생하는지**를 보는 용도로 읽어야 합니다.")
    add("")

    add("### 8.6 질문유형별 (상위 12개)")
    add("")
    top_types = dict(list(summary["groups"]["question_type"].items())[:12])
    lines.extend(_group_table(top_types, quality_columns, "질문유형"))
    add("")

    # ------------------------------------------------------------------
    diagnostics = summary["diagnostics"]
    add("## 9. 주요 발견")
    add("")
    add("### 9.1 근거 검증 계층은 정상 작동, 병목은 검색 단계")
    add("")
    add(
        f"- 근거계획 반려 **{diagnostics['plan_rejected_total']}건** 중 "
        f"**{diagnostics['plan_rejected_without_gold_in_context']}건**은 정답 문서가 실제로 문맥에 "
        f"없었습니다(정답 문서가 있었는데 반려한 경우는 "
        f"{diagnostics['plan_rejected_with_gold_in_context']}건)."
    )
    add(
        f"- 즉 \"{'지식베이스에 근거 없음'}\" 응답은 대부분 **검색 실패의 정직한 반영**이며, "
        f"근거계획 선검증·사후감사 계층 자체는 의도대로 동작합니다 "
        f"(사후감사 통과율 {_fmt(grounding['audit_pass_rate'], percent=True)}, "
        f"미근거 주장 {_fmt(grounding['unsupported_claim_rate'], percent=True)})."
    )
    add(
        f"- 답변가능 질문 {counts['answerable']}건 중 "
        f"**{diagnostics['false_abstention_count']}건"
        f"({_fmt(diagnostics['false_abstention_rate'], percent=True)})**이 불필요하게 거절되었습니다. "
        f"이것이 현재 체감 품질을 가장 크게 떨어뜨리는 요인입니다."
    )
    add("")
    add("### 9.2 컬렉션 균등 배분이 문맥의 대부분을 낭비")
    add("")
    add(
        f"- 설정이 `final_top_k={system.get('final_top_k')}` · "
        f"`max_per_collection={system.get('max_per_collection')}` · "
        f"namespace {len(system.get('search_collections') or [])}개이므로 "
        f"질문 성격과 무관하게 컬렉션마다 정확히 "
        f"{system.get('max_per_collection')}청크가 배정됩니다."
    )
    add(f"- 실제 문맥 점유: `{retrieval['collection_share']}` — 완전 균등.")
    add(
        f"- 정답 문서가 속한 namespace 외 청크가 문맥의 "
        f"**{_fmt(diagnostics['off_domain_context_share'], percent=True)}**를 차지합니다. "
        f"근거정밀도가 {_fmt(overall.get('context_precision_id'))}에 머무는 직접적 원인입니다."
    )
    add(
        f"- 컬렉션 상한 때문에 병합 과정에서 Hit@3가 "
        f"{_fmt(overall.get('candidate_hit@3'), percent=True)} → "
        f"{_fmt(overall.get('hit@3'), percent=True)}로 하락합니다."
    )
    add("")
    add("### 9.3 검색 실패의 대부분은 \"맞는 문서, 틀린 섹션\"")
    add("")
    add(
        f"- 정확 청크 Hit@3 {_fmt(overall.get('hit@3'), percent=True)} vs "
        f"원천 문서 Hit@3 {_fmt(overall.get('group_hit@3'), percent=True)}."
    )
    add(
        f"- 정답 문서가 지정된 질문 {diagnostics['section_mismatch_denominator']}건 중 "
        f"**{diagnostics['section_mismatch_count']}건"
        f"({_fmt(diagnostics['section_mismatch_rate'], percent=True)})**은 정답 청크를 놓쳤지만 "
        f"같은 질병·의약품의 **다른 섹션**은 회수했습니다."
    )
    add(
        "- 예: \"파킨슨병을 예방하려면?\" → 정답은 `예방` 섹션인데 `정의/증상` 섹션이 회수됨. "
        "임베딩이 질문의 **섹션 의도**(예방·원인·증상·기준)를 구분하지 못하고 질병명 유사도에 지배됩니다."
    )
    add("")
    add("### 9.4 Intent 라우팅")
    add("")
    add(
        f"- 답변불가 질문 {counts['unanswerable']}건 중 대부분이 `ignore`로 조기 차단되어 "
        f"거절 정확도 {_fmt(unanswerable.get('abstention_correct'), percent=True)}를 기록했습니다."
    )
    add(
        f"- 반면 답변가능 질문 **{diagnostics['intent_misrouted_count']}건"
        f"({_fmt(diagnostics['intent_misrouted_rate'], percent=True)})**이 "
        f"`ignore`/`general_chat`으로 잘못 라우팅되어 검색 자체가 실행되지 않았습니다. "
        f"이들의 평균 분류 신뢰도는 "
        f"{_fmt(diagnostics['intent_misrouted_mean_confidence'])}로 "
        f"임계값 {system.get('intent_min_confidence')}를 넘어 저신뢰로 걸러지지도 않았습니다."
    )
    add(
        f"- 전체 저신뢰 비율은 {_fmt(intent['uncertain_rate'], percent=True)}에 불과해 "
        f"현재 임계값이 오분류를 거의 포착하지 못합니다."
    )
    add("")
    add("### 9.5 지연시간 구성")
    add("")
    add(
        f"- TTFB p50 {_fmt_ms(latency['first_token_ms']['p50'])}ms의 최대 기여 구간은 "
        f"**근거계획 생성**(p50 {_fmt_ms(latency['plan_ms']['p50'])}ms)이며, "
        f"검색은 {_fmt_ms(latency['search_ms']['p50'])}ms, "
        f"임베딩·분류는 {_fmt_ms(latency['embed_ms']['p50'])}ms 수준으로 무시할 만합니다."
    )
    add(
        f"- 사후 감사(p50 {_fmt_ms(latency['audit_ms']['p50'])}ms)는 스트리밍 이후에 실행되어 "
        f"TTFB에는 영향이 없지만 종단 지연 "
        f"p50 {_fmt_ms(latency['end_to_end_ms']['p50'])}ms의 큰 부분을 차지합니다."
    )
    add("")
    add("### 9.6 개선 우선순위 (제안)")
    add("")
    add("| 우선순위 | 조치 | 근거 | 기대 효과 |")
    add("|---|---|---|---|")
    add(
        "| 1 | Intent에 **대상 컬렉션 라우팅** 추가 또는 `max_per_collection` 폐지 후 "
        "점수 기반 선택 | 문맥의 "
        f"{_fmt(diagnostics['off_domain_context_share'], percent=True)}가 무관 컬렉션 "
        "| 근거정밀도 대폭 개선, 근거계획 반려 감소 |"
    )
    add(
        "| 2 | `top_k_per_collection` 상향(3→10) + 섹션 인지 재순위화(rerank) "
        f"| 섹션 불일치 {_fmt(diagnostics['section_mismatch_rate'], percent=True)} "
        "| 정확 청크 Hit@k를 원천 문서 Hit@k 수준으로 근접 |"
    )
    add(
        "| 3 | 질병명+섹션명을 청크 임베딩 텍스트에 강화 반영하거나 하이브리드(BM25+dense) 검색 도입 "
        "| 질문의 섹션 의도가 코사인 유사도에 반영되지 않음 | 예방·원인·기준 유형 질문 회수율 개선 |"
    )
    add(
        f"| 4 | Intent 임계값 재보정(현재 {system.get('intent_min_confidence')}) 및 "
        "장문 증상 서술 학습데이터 보강 "
        f"| 답변가능 {diagnostics['intent_misrouted_count']}건 오라우팅 | 불필요한 즉시 거절 제거 |"
    )
    add(
        f"| 5 | 근거계획 프롬프트 경량화 또는 단순 질의 시 계획 단계 생략 "
        f"| 계획 생성이 TTFB p50의 최대 구간({_fmt_ms(latency['plan_ms']['p50'])}ms) "
        "| TTFB 단축 |"
    )
    add("")

    # ------------------------------------------------------------------
    add("## 10. 오류 및 제외 건")
    add("")
    if summary["errors"]:
        add("| question_id | 오류 |")
        add("|---|---|")
        for error in summary["errors"][:20]:
            add(f"| `{error['question_id']}` | {error['error']} |")
    else:
        add("파이프라인 실행 오류 없음.")
    add("")
    if ragas_summary and ragas_summary.get("skipped"):
        skipped_reasons = Counter(entry["reason"] for entry in ragas_summary["skipped"])
        add(f"- ragas 채점 제외 {len(ragas_summary['skipped'])}건: `{dict(skipped_reasons)}`")
        add("")

    # ------------------------------------------------------------------
    add("## 11. 지표 정의")
    add("")
    add("| 지표 | 계산 방식 |")
    add("|---|---|")
    add("| 근거재현율 (문서ID) | (최종문맥 ∩ `gold_document_ids`) 개수 ÷ `gold_document_ids` 개수 |")
    add("| 근거정밀도 (문서ID) | (최종문맥 ∩ `acceptable_document_ids`) 개수 ÷ 최종문맥 청크 수 |")
    add("| Hit@k | 상위 k개 문맥에 정답 문서가 1개 이상 포함되면 1 |")
    add("| MRR@10 | 첫 정답 문서 순위의 역수 평균 |")
    add("| 출처ID일치율 | LLM 근거계획이 인용한 `C{n}` → `record_id` 변환 후 정답 문서 비율 |")
    add("| 근거충실도 | ragas faithfulness — 답변 문장을 주장 단위로 분해해 문맥 뒷받침 여부 판정 |")
    add("| 정답일치율 | ragas answer_correctness — 참조 정답 대비 사실 TP/FP/FN + 의미 유사도 가중합 |")
    add("| TTFB | 요청 시작부터 사용자에게 첫 토큰이 전달되기까지 (Guard+임베딩+분류+검색+근거계획+생성 첫 토큰) |")
    add("| 거절 정확도 | 시스템 거절 여부가 골든셋 `answerable` 라벨과 일치하는 비율 |")
    add("")

    # ------------------------------------------------------------------
    add("## 12. 재현 방법")
    add("")
    add("```bash")
    add("# 1) 단위 테스트")
    add("PYTHONPATH=. python -m pytest tests -q")
    add("")
    add("# 2) 골든셋 종단 실행")
    add(
        f"PYTHONPATH=. python tests/eval/run_golden_eval.py "
        f"--sample-size {meta.get('sample_size_requested')} --workers {meta.get('workers')} "
        f"--seed {meta.get('seed')}"
    )
    add("")
    add("# 3) ragas 채점")
    add("PYTHONPATH=. python tests/eval/score_ragas.py --workers 4")
    add("")
    add("# 4) 집계 및 리포트")
    add("PYTHONPATH=. python tests/eval/aggregate_report.py")
    add("```")
    add("")
    add("## 13. 산출물")
    add("")
    add("| 파일 | 내용 |")
    add("|---|---|")
    add("| `per_question.jsonl` | 질문별 intent·확률·검색 후보·최종 문맥·근거계획·답변·감사·단계별 시간 원본 |")
    add("| `per_question.csv` | 질문별 핵심 지표 요약 (Excel 검토용, UTF-8 BOM) |")
    add("| `ragas_scores.jsonl` | 질문별 ragas 4개 지표 점수 |")
    add("| `ragas_summary.json` | ragas 채점 메타·평균 |")
    add("| `metrics_summary.json` | 전체·세그먼트 집계 지표 |")
    add("| `run_meta.json` | 실행 환경·시스템 설정 스냅샷 |")
    add("| `report.md` | 본 리포트 |")
    add("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="평가 결과 집계 및 리포트 생성")
    parser.add_argument("--in-dir", type=Path, default=Path("output") / "golden_test")
    args = parser.parse_args()

    in_dir = args.in_dir if args.in_dir.is_absolute() else ROOT / args.in_dir
    records = [
        json.loads(line)
        for line in (in_dir / "per_question.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    meta = json.loads((in_dir / "run_meta.json").read_text(encoding="utf-8"))

    # 문서 ID 정규화 규칙이 갱신될 수 있으므로 원시 결과에서 결정적 지표를 다시 계산한다.
    # 임베딩이 필요한 답변 유사도만 실행 시점 값을 그대로 유지한다.
    for record in records:
        if record.get("status") != "ok":
            continue
        similarity = record.get("metrics", {}).get("answer_semantic_similarity")
        record["metrics"] = deterministic_metrics(record)
        record["metrics"]["answer_semantic_similarity"] = similarity

    ragas_scores: dict[str, dict] = {}
    ragas_path = in_dir / "ragas_scores.jsonl"
    if ragas_path.is_file():
        for line in ragas_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                payload = json.loads(line)
                ragas_scores[payload.pop("question_id")] = payload

    ragas_summary = None
    ragas_summary_path = in_dir / "ragas_summary.json"
    if ragas_summary_path.is_file():
        ragas_summary = json.loads(ragas_summary_path.read_text(encoding="utf-8"))

    summary = build_summary(records, ragas_scores)

    def _json_safe(value):
        if isinstance(value, float):
            return None if value != value else value
        if isinstance(value, dict):
            return {k: _json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_safe(v) for v in value]
        return value

    (in_dir / "metrics_summary.json").write_text(
        json.dumps(_json_safe(summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    write_csv(records, ragas_scores, in_dir / "per_question.csv")
    (in_dir / "report.md").write_text(
        build_report(meta, summary, ragas_summary), encoding="utf-8"
    )

    print(f"[report] metrics_summary.json / per_question.csv / report.md 저장: {in_dir}")
    print(f"[report] 근거충실도 {_fmt(summary['overall'].get('faithfulness'))} "
          f"· 정답일치율 {_fmt(summary['overall'].get('answer_correctness'))} "
          f"· 근거재현율 {_fmt(summary['overall'].get('context_recall_id'))} "
          f"· 출처ID일치율 {_fmt(summary['overall'].get('citation_accuracy'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
