#!/usr/bin/env python3
"""HEAPY Intent v6 Test 또는 Blind split을 독립적으로 평가한다.

작성자: 김진우
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from langchain_huggingface import HuggingFaceEmbeddings

from app.services.safety_guard import check_safety_guard
from classifier.script.intent_v6_utils import (
    CONFIDENCE_THRESHOLD,
    EMBED_DIMENSION,
    EMBED_MODEL,
    LABELS,
    LABEL_TO_ID,
    ROOT,
    classification_metrics,
    classification_metrics_from_predictions,
    load_checkpoint,
    load_dataset,
    logits_from_checkpoint,
    prediction_rows,
    write_json,
    write_jsonl,
)


DEFAULT_CHECKPOINT = ROOT / "classifier/artifacts/intent-v6/best_model.json"
DEFAULT_OUTPUT_DIR = ROOT / "classifier/artifacts/intent-v6"
SPLIT_PATHS = {
    "test": ROOT / "classifier/data/HEAPY_intent_v6_test.jsonl",
    "blind": ROOT / "classifier/data/HEAPY_intent_v6_blind48.jsonl",
}


def _embed(
    examples: list[dict[str, str]],
    device: torch.device,
) -> torch.Tensor:
    """평가 문장을 학습과 동일한 Frozen 모델로 임베딩한다."""
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": device.type},
    )
    vectors = embeddings.embed_documents([example["text"] for example in examples])
    if any(len(vector) != EMBED_DIMENSION for vector in vectors):
        raise ValueError(f"임베딩은 모두 {EMBED_DIMENSION}차원이어야 합니다.")
    return torch.tensor(vectors, dtype=torch.float32)


def _guard_rows(
    classifier_rows: list[dict[str, Any]],
    *,
    guard_routing: str = "legacy_ignore",
) -> list[dict[str, Any]]:
    """Linear 예측에 Safety Guard 정책 메타데이터를 추가한다."""
    rows: list[dict[str, Any]] = []
    for classifier_row in classifier_rows:
        guard = check_safety_guard(classifier_row["text"])
        legacy_override = guard_routing == "legacy_ignore" and guard.triggered
        final_label = "ignore" if legacy_override else classifier_row["predicted_label"]
        final_confidence = 1.0 if legacy_override else classifier_row["confidence"]
        final_uncertain = False if legacy_override else classifier_row["uncertain"]
        rows.append(
            {
                "text": classifier_row["text"],
                "true_label": classifier_row["true_label"],
                "predicted_label": final_label,
                "confidence": final_confidence,
                "uncertain": final_uncertain,
                "classifier_predicted_label": classifier_row["predicted_label"],
                "classifier_confidence": classifier_row["confidence"],
                "classifier_uncertain": classifier_row["uncertain"],
                "probabilities": classifier_row["probabilities"],
                "guard_triggered": guard.triggered,
                "guard_reason": guard.reason,
                "matched_patterns": guard.matched_patterns,
                "risk_level": guard.risk_level.value,
                "restricted_actions": guard.restricted_actions,
                "response_policy": guard.response_policy,
                "emergency": guard.emergency,
                "correct": final_label == classifier_row["true_label"],
            }
        )
    return rows


def _metrics_for_guard_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    true_ids = [LABEL_TO_ID[row["true_label"]] for row in rows]
    predicted_ids = [LABEL_TO_ID[row["predicted_label"]] for row in rows]
    return classification_metrics_from_predictions(true_ids, predicted_ids)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    """best checkpoint로 지정 split을 평가하고 문장별 결과를 저장한다."""
    checkpoint_path = args.checkpoint.resolve()
    data_path = (args.data or SPLIT_PATHS[args.split]).resolve()
    output_dir = args.output_dir.resolve()
    checkpoint = load_checkpoint(checkpoint_path)
    examples = load_dataset(data_path)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"평가 split: {args.split}")
    print(f"평가 데이터: {data_path}")
    print(f"체크포인트: {checkpoint_path}")
    print(f"임베딩 device: {device.type}")
    features = _embed(examples, device)
    logits = logits_from_checkpoint(features, checkpoint)
    targets = torch.tensor(
        [LABEL_TO_ID[example["label"]] for example in examples],
        dtype=torch.long,
    )
    loss = float(torch.nn.CrossEntropyLoss()(logits, targets).item())
    classifier_metrics = classification_metrics(logits, targets, loss)
    confidence_threshold = float(
        checkpoint.get("confidence_threshold", CONFIDENCE_THRESHOLD)
    )
    classifier_rows = prediction_rows(examples, logits, confidence_threshold)
    for row in classifier_rows:
        row["correct"] = row["predicted_label"] == row["true_label"]

    guard_rows = _guard_rows(
        classifier_rows,
        guard_routing=args.guard_routing,
    )
    guard_metrics = _metrics_for_guard_rows(guard_rows)
    classifier_errors = [row for row in classifier_rows if not row["correct"]]
    guard_errors = [row for row in guard_rows if not row["correct"]]
    result = {
        "schema_version": 1,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "split": args.split,
        "data_file": data_path.name,
        "checkpoint_file": checkpoint_path.name,
        "model_version": checkpoint["model_version"],
        "embedding_model": checkpoint["embedding_model"],
        "labels": list(LABELS),
        "confidence_threshold": confidence_threshold,
        "guard_routing": args.guard_routing,
        "classifier_only": {
            "metrics": classifier_metrics,
            "misclassified_count": len(classifier_errors),
            "misclassified": classifier_errors,
        },
        "classifier_with_safety_guard": {
            "metrics": guard_metrics,
            "guard_trigger_count": sum(
                int(row["guard_triggered"]) for row in guard_rows
            ),
            "misclassified_count": len(guard_errors),
            "misclassified": guard_errors,
        },
    }

    version_tag = str(checkpoint["model_version"]).split("-")[1]
    prefix = f"{args.split}_{version_tag}"
    write_json(output_dir / f"{prefix}_evaluation.json", result)
    write_jsonl(output_dir / f"{prefix}_predictions.jsonl", guard_rows)
    write_jsonl(output_dir / f"{prefix}_misclassified.jsonl", guard_errors)

    for name, metrics in (
        ("Linear classifier only", classifier_metrics),
        (f"Linear classifier + Safety Guard ({args.guard_routing})", guard_metrics),
    ):
        loss_text = (
            f"{metrics['loss']:.4f}"
            if metrics.get("loss") is not None
            else "-"
        )
        print(
            f"{name}: loss={loss_text}, "
            f"accuracy={metrics['accuracy']:.4f}, "
            f"macro_f1={metrics['macro_f1']:.4f}"
        )
        print(f"  confusion_matrix={metrics['confusion_matrix']}")
    print(f"최종 오분류: {len(guard_errors)}건")
    print(f"평가 저장: {output_dir / f'{prefix}_evaluation.json'}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("test", "blind"), required=True)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--data",
        type=Path,
        help="기본 split 파일 대신 사용할 JSONL",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--guard-routing",
        choices=("legacy_ignore", "metadata_only"),
        default="legacy_ignore",
        help="Safety Guard가 intent를 ignore로 덮어쓸지 여부",
    )
    return parser


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        args = build_parser().parse_args()
        evaluate(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
