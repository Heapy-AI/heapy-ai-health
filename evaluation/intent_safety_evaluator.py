#!/usr/bin/env python3
"""골든데이터셋에서 Intent v7과 Safety 정책 경로를 평가한다.

작성자: 김진우
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import EMBED_MODEL, INTENT_MIN_CONFIDENCE, INTENT_MODEL_PATH, ROOT
from app.services.intent_classifier import LinearIntentClassifier
from app.services.safety_guard import check_safety_guard


DEFAULT_GOLD_PATH = ROOT / "data/RAG_골든데이터셋_최종_질병_복약_건강검진_2290.jsonl"
DEFAULT_OUTPUT_ROOT = ROOT / "evaluation/results/intent_safety"
MEDICAL_DECISION_TYPES = {
    "답변불가·개인 진단 요청",
    "답변불가·확정진단",
    "답변불가·개인 용량 변경",
    "답변불가·개인 복용 판단",
    "답변불가·개인 예후 단정",
}


def _load_rows(path: Path, split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSON 객체가 아닙니다: {path}:{line_number}")
            if row.get("split") == split:
                rows.append(row)
    if not rows:
        raise ValueError(f"평가할 문항이 없습니다: split={split}")
    return rows


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def evaluate(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """골든 질문의 Intent 분포와 Safety 정책 탐지율을 계산한다."""
    rows = _load_rows(args.gold_path.resolve(), args.split)
    embedder = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
    )
    classifier = LinearIntentClassifier.from_file(
        args.checkpoint.resolve(),
        args.minimum_confidence,
    )
    questions = [str(row["question"]) for row in rows]
    embeddings = embedder.embed_documents(questions)

    results: list[dict[str, Any]] = []
    for row, embedding in zip(rows, embeddings, strict=True):
        prediction = classifier.predict(embedding)
        safety = check_safety_guard(str(row["question"]))
        results.append(
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "domain": row["domain"],
                "question_type": row["question_type"],
                "answerable": bool(row["answerable"]),
                "expected_behavior": row["expected_behavior"],
                "intent": prediction.intent.value,
                "confidence": prediction.confidence,
                "uncertain": prediction.uncertain,
                "risk_level": safety.risk_level.value,
                "restricted_actions": safety.restricted_actions,
                "guard_reason": safety.reason,
                "emergency": safety.emergency,
            }
        )

    intent_counts = Counter(result["intent"] for result in results)
    risk_counts = Counter(result["risk_level"] for result in results)
    ignore_rows = [result for result in results if result["intent"] == "ignore"]
    uncertain_rows = [result for result in results if result["uncertain"]]
    decision_rows = [
        result
        for result in results
        if result["question_type"] in MEDICAL_DECISION_TYPES
    ]
    protected_decision_rows = [
        result
        for result in decision_rows
        if result["risk_level"] != "normal"
    ]
    expected_behavior_counts: dict[str, dict[str, int]] = {}
    for behavior in sorted({result["expected_behavior"] for result in results}):
        selected = [
            result for result in results if result["expected_behavior"] == behavior
        ]
        expected_behavior_counts[behavior] = dict(
            Counter(result["intent"] for result in selected)
        )

    summary = {
        "schema_version": 1,
        "evaluated_at": datetime.now().astimezone().isoformat(),
        "split": args.split,
        "question_count": len(results),
        "model_version": classifier.model_version,
        "intent_counts": dict(intent_counts),
        "risk_counts": dict(risk_counts),
        "uncertain_count": len(uncertain_rows),
        "uncertain_rate": _rate(len(uncertain_rows), len(results)),
        "health_query_ignore_count": len(ignore_rows),
        "health_query_ignore_rate": _rate(len(ignore_rows), len(results)),
        "medical_decision_count": len(decision_rows),
        "medical_decision_policy_count": len(protected_decision_rows),
        "medical_decision_policy_rate": _rate(
            len(protected_decision_rows),
            len(decision_rows),
        ),
        "intent_by_expected_behavior": expected_behavior_counts,
        "ignored_questions": ignore_rows,
        "unprotected_medical_decisions": [
            result
            for result in decision_rows
            if result["risk_level"] == "normal"
        ],
    }
    return summary, results


def _save_results(
    output_root: Path,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
) -> Path:
    run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root.resolve() / run_name
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "per_question_results.jsonl").open(
        "w",
        encoding="utf-8",
    ) as file:
        for result in results:
            file.write(json.dumps(result, ensure_ascii=False) + "\n")
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-path", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--split", choices=("calibration", "test"), default="calibration")
    parser.add_argument("--checkpoint", type=Path, default=INTENT_MODEL_PATH)
    parser.add_argument(
        "--minimum-confidence",
        type=float,
        default=INTENT_MIN_CONFIDENCE,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary, results = evaluate(args)
    output_dir = _save_results(args.output_root, summary, results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"평가 결과 저장 완료: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
