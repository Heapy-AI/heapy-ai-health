"""골든 데이터셋으로 RAG 종단 파이프라인을 실행하고 원시 결과를 기록한다.

실행 예:
    PYTHONPATH=. python evaluation/eval/run_golden_eval.py --sample-size 150 --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep

try:  # Windows 콘솔에서 한글·이모지 출력 보호
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.chat_orchestrator import (  # noqa: E402
    GENERAL_IGNORE_ANSWER,
    SAFETY_IGNORE_ANSWER,
)
from app.services.grounded_rag import NOT_GROUNDED_ANSWER  # noqa: E402

from evaluation.eval import metrics as M  # noqa: E402
from evaluation.eval.golden_dataset import (  # noqa: E402
    DEFAULT_DATASET,
    GoldenItem,
    load_dataset,
    stratified_sample,
)
from evaluation.eval.instrumentation import (  # noqa: E402
    SharedServices,
    StageTimings,
    build_instrumented_orchestrator,
    build_shared_services,
)

ABSTENTION_ANSWERS = {
    NOT_GROUNDED_ANSWER,
    GENERAL_IGNORE_ANSWER,
    SAFETY_IGNORE_ANSWER,
}


def _json_safe(value):
    """NaN/Infinity를 null로 바꿔 표준 JSON으로 저장한다."""
    if isinstance(value, float):
        return None if value != value or value in (float("inf"), float("-inf")) else value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _document_record(document, rank: int) -> dict:
    """검색 문서를 결과 파일에 남길 형태로 요약한다."""
    metadata = document.metadata
    return {
        "rank": rank,
        "record_id": str(metadata.get("record_id", "")),
        "collection": str(metadata.get("collection", "")),
        "score": float(metadata.get("score", 0.0) or 0.0),
        "source_label": metadata.get("source_label", ""),
        "source": metadata.get("source", ""),
        "section": metadata.get("section", ""),
        "title": metadata.get("disease") or metadata.get("title") or "",
        "text": document.page_content,
    }


def _candidate_records(raw_search) -> list[dict]:
    """병합 전 원시 후보를 점수순으로 정리한다."""
    if raw_search is None:
        return []
    ranked = sorted(
        raw_search.documents,
        key=lambda d: -float(d.metadata.get("score", 0.0) or 0.0),
    )
    return [_document_record(doc, rank) for rank, doc in enumerate(ranked, start=1)]


def _is_abstention(answer: str, grounded) -> bool:
    return M.is_abstention(answer, grounded)


def evaluate_one(
    item: GoldenItem,
    shared: SharedServices,
    max_retries: int,
) -> dict:
    """질문 1건을 운영 스트리밍 경로로 실행하고 결과 레코드를 만든다."""
    last_error = ""
    for attempt in range(max_retries + 1):
        timings = StageTimings()
        orchestrator = build_instrumented_orchestrator(shared, timings)
        started_at = perf_counter()
        first_token_at: float | None = None
        result = None
        streamed: list[str] = []

        try:
            for event in orchestrator.stream_answer(item.question):
                if event.event == "token":
                    if first_token_at is None:
                        first_token_at = perf_counter()
                    streamed.append(event.text)
                elif event.event == "complete":
                    result = event.result
            if result is None:
                raise RuntimeError("complete 이벤트를 받지 못했습니다.")
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                sleep(2.0 * (attempt + 1))
                continue
            return {
                "question_id": item.question_id,
                "question": item.question,
                "status": "error",
                "error": last_error,
                "traceback": traceback.format_exc(limit=3),
                "timings": timings.as_dict(),
            }

        timings.end_to_end_ms = (perf_counter() - started_at) * 1000.0
        if first_token_at is not None:
            timings.first_token_ms = (first_token_at - started_at) * 1000.0

        retrieved = [
            _document_record(doc, rank)
            for rank, doc in enumerate(result.documents, start=1)
        ]
        record = {
            "question_id": item.question_id,
            "question": item.question,
            "status": "ok",
            "attempt": attempt + 1,
            # 골든 라벨
            "gold": {
                "split": item.split,
                "domain": item.domain,
                "question_type": item.question_type,
                "difficulty": item.difficulty,
                "answerable": item.answerable,
                "expected_behavior": item.expected_behavior,
                "target": item.target,
                "reference_answer": item.reference_answer,
                "gold_document_ids": item.gold_document_ids,
                "acceptable_document_ids": item.acceptable_document_ids,
                "gold_contexts": item.gold_contexts,
                "source_label": item.source_label,
                "source_uri": item.source_uri,
            },
            # Intent 분류
            "intent": result.intent.value,
            "intent_confidence": result.confidence,
            "intent_probabilities": result.probabilities,
            "intent_uncertain": result.uncertain,
            "intent_source": result.intent_source,
            "intent_model_version": result.model_version,
            "guard_triggered": result.guard_triggered,
            "guard_reason": result.guard_reason,
            "matched_patterns": result.matched_patterns,
            # 검색
            "searched_collections": result.searched_collections,
            "failed_collections": result.failed_collections,
            "candidate_documents": _candidate_records(timings.raw_search),
            "retrieved_documents": retrieved,
            "top_score": retrieved[0]["score"] if retrieved else None,
            "mean_score": (
                sum(d["score"] for d in retrieved) / len(retrieved) if retrieved else None
            ),
            # 생성·검증
            "answer": result.answer,
            "answer_length": len(result.answer or ""),
            "grounded": result.grounded,
            "cited_chunk_ids": result.cited_chunk_ids,
            "verification_method": result.verification_method,
            "verification_reason": result.verification_reason,
            "grounding_errors": result.grounding_errors,
            "unsupported_claims": result.unsupported_claims,
            "grounding_plan": result.grounding_plan,
            "audit_status": result.audit_status,
            "audit_summary": result.audit_summary,
            # 처리 속도
            "timings": timings.as_dict(),
        }
        record["metrics"] = M.deterministic_metrics(record)
        return record

    return {
        "question_id": item.question_id,
        "question": item.question,
        "status": "error",
        "error": last_error or "unknown",
    }


def add_answer_similarity(records: list[dict], shared: SharedServices) -> None:
    """답변과 참조 정답의 임베딩 코사인 유사도를 사후 계산한다(지연시간 제외)."""
    for record in records:
        if record.get("status") != "ok":
            continue
        reference = record["gold"]["reference_answer"]
        answer = record["answer"]
        if not reference or not answer:
            record["metrics"]["answer_semantic_similarity"] = float("nan")
            continue
        with shared.embed_lock:
            answer_vector = shared.vector_search.embed_query(answer)
            reference_vector = shared.vector_search.embed_query(reference)
        record["metrics"]["answer_semantic_similarity"] = M.cosine_similarity(
            answer_vector, reference_vector
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="골든 데이터셋 RAG 종단 평가")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=150,
        help="층화 표본 크기 (0 또는 전체 크기 이상이면 전량 평가)",
    )
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--out-dir", type=Path, default=Path("output") / "golden_test")
    parser.add_argument(
        "--split",
        default="",
        help="특정 split만 평가 (예: test, calibration)",
    )
    parser.add_argument("--limit", type=int, default=0, help="표본에서 앞 N건만 실행")
    args = parser.parse_args()

    dataset_path = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    items = load_dataset(dataset_path)
    if args.split:
        items = [item for item in items if item.split == args.split]
    sampled = stratified_sample(items, args.sample_size, args.seed)
    if args.limit:
        sampled = sampled[: args.limit]

    print(f"[eval] 데이터셋 {dataset_path.name} - 전체 {len(items)}건 중 {len(sampled)}건 평가")
    print("[eval] 공유 서비스 준비 중 (임베딩 모델 로딩·Pinecone 연결)...")
    setup_started = perf_counter()
    shared = build_shared_services()
    setup_seconds = perf_counter() - setup_started
    print(f"[eval] 준비 완료 ({setup_seconds:.1f}s) - {shared.config_snapshot}")

    records: list[dict] = []
    lock = threading.Lock()
    started_at = perf_counter()

    def worker(index_item: tuple[int, GoldenItem]) -> dict:
        index, item = index_item
        record = evaluate_one(item, shared, args.max_retries)
        with lock:
            records.append(record)
            done = len(records)
            if done % 10 == 0 or done == len(sampled):
                elapsed = perf_counter() - started_at
                rate = done / elapsed if elapsed else 0
                remaining = (len(sampled) - done) / rate if rate else 0
                print(
                    f"[eval] {done}/{len(sampled)} "
                    f"({elapsed:.0f}s 경과, 남은 예상 {remaining:.0f}s)",
                    flush=True,
                )
        return record

    if args.workers <= 1:
        for pair in enumerate(sampled):
            worker(pair)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            list(executor.map(worker, enumerate(sampled)))

    wall_seconds = perf_counter() - started_at
    print(f"[eval] 실행 완료 {wall_seconds:.0f}s - 답변 유사도 계산 중...")
    add_answer_similarity(records, shared)

    records.sort(key=lambda r: r["question_id"])
    output_path = out_dir / "per_question.jsonl"
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(_json_safe(record), ensure_ascii=False, allow_nan=False) + "\n"
            )

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path.relative_to(ROOT)),
        "dataset_total": len(items),
        "evaluated": len(records),
        "sample_size_requested": args.sample_size,
        "split_filter": args.split or None,
        "seed": args.seed,
        "workers": args.workers,
        "max_retries": args.max_retries,
        "setup_seconds": round(setup_seconds, 2),
        "wall_seconds": round(wall_seconds, 2),
        "questions_per_second": round(len(records) / wall_seconds, 4) if wall_seconds else None,
        "errors": sum(1 for r in records if r.get("status") != "ok"),
        "system": shared.config_snapshot,
    }
    (out_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[eval] 저장 완료: {output_path}")
    print(f"[eval] 오류 {meta['errors']}건 / 총 {len(records)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
