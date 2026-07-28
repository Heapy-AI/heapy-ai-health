#!/usr/bin/env python3
"""Intent v5와 Safety Guard를 공통 외부 평가셋에서 검증한다.

작성자: 김진우
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import torch
from langchain_huggingface import HuggingFaceEmbeddings


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.safety_guard import check_safety_guard


LABELS = ("simple_lookup", "comprehensive", "general_chat", "ignore")
MODEL_PATHS = {
    "v5": ROOT / "classifier/artifacts/intent_linear_v5_candidate.json",
}
V5_DATASET_PATH = ROOT / "classifier/data/HEAPY_intent_dataset_v3_500.csv"
BOUNDARY_PATH = (
    ROOT / "classifier/evaluation/fixtures/intent_boundary_60.jsonl"
)
BLIND_PATH = ROOT / "classifier/evaluation/fixtures/intent_blind_48.jsonl"
OUTPUT_DIR = ROOT / "classifier/evaluation/intent_v5"
KEY_BLIND_IDS = {"B-CP07", "B-CP09", "B-IG08"}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _metrics(expected: list[str], predicted: list[str]) -> dict[str, Any]:
    label_index = {label: index for index, label in enumerate(LABELS)}
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for truth, guess in zip(expected, predicted, strict=True):
        matrix[label_index[truth]][label_index[guess]] += 1

    precisions: list[float] = []
    recalls: list[float] = []
    f1_scores: list[float] = []
    for index in range(len(LABELS)):
        true_positive = matrix[index][index]
        predicted_count = sum(row[index] for row in matrix)
        expected_count = sum(matrix[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / expected_count if expected_count else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
    correct = sum(matrix[index][index] for index in range(len(LABELS)))
    return {
        "count": len(expected),
        "accuracy": correct / len(expected),
        "macro_precision": sum(precisions) / len(precisions),
        "macro_recall": sum(recalls) / len(recalls),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "confusion_matrix": matrix,
    }


def _predict(
    artifact: dict[str, Any],
    vectors: torch.Tensor,
) -> tuple[list[str], list[float], list[list[float]]]:
    weights = torch.tensor(artifact["weights"], dtype=torch.float32)
    bias = torch.tensor(artifact["bias"], dtype=torch.float32)
    probabilities = torch.softmax(vectors @ weights.T + bias, dim=1)
    indices = probabilities.argmax(dim=1)
    return (
        [LABELS[index] for index in indices.tolist()],
        probabilities.max(dim=1).values.tolist(),
        probabilities.tolist(),
    )


def _error_rows(
    cases: list[dict[str, Any]],
    positions: list[int],
    predicted: list[str],
    confidence: list[float],
    probabilities: list[list[float]],
    guards: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index in positions:
        final_intent = guards[index]["final_intent"] if guards else predicted[index]
        if final_intent == cases[index]["expected_intent"]:
            continue
        errors.append(
            {
                "test_id": cases[index]["test_id"],
                "text": cases[index]["text"],
                "expected": cases[index]["expected_intent"],
                "classifier_intent": predicted[index],
                "final_intent": final_intent,
                "confidence": confidence[index],
                "uncertain": confidence[index] < 0.55,
                "probabilities": dict(
                    zip(LABELS, probabilities[index], strict=True)
                ),
                "guard_triggered": bool(guards and guards[index]["guard_triggered"]),
                "guard_reason": guards[index]["guard_reason"] if guards else None,
            }
        )
    return errors


def _write_predictions_csv(
    path: Path,
    cases: list[dict[str, Any]],
    independent_positions: set[int],
    predicted: list[str],
    confidence: list[float],
    probabilities: list[list[float]],
    guards: list[dict[str, Any]],
    boundary_count: int,
) -> None:
    fieldnames = [
        "dataset", "independent_54", "test_id", "text", "expected_intent",
        "classifier_intent", "confidence", "uncertain",
        "prob_simple_lookup", "prob_comprehensive", "prob_general_chat",
        "prob_ignore", "guard_triggered", "guard_reason", "matched_patterns",
        "final_intent", "classifier_correct", "final_correct",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for index, case in enumerate(cases):
            final_intent = guards[index]["final_intent"]
            writer.writerow(
                {
                    "dataset": "기존 60" if index < boundary_count else "Blind 48",
                    "independent_54": index in independent_positions,
                    "test_id": case["test_id"],
                    "text": case["text"],
                    "expected_intent": case["expected_intent"],
                    "classifier_intent": predicted[index],
                    "confidence": round(confidence[index], 6),
                    "uncertain": confidence[index] < 0.55,
                    "prob_simple_lookup": round(probabilities[index][0], 6),
                    "prob_comprehensive": round(probabilities[index][1], 6),
                    "prob_general_chat": round(probabilities[index][2], 6),
                    "prob_ignore": round(probabilities[index][3], 6),
                    "guard_triggered": guards[index]["guard_triggered"],
                    "guard_reason": guards[index]["guard_reason"] or "",
                    "matched_patterns": " | ".join(guards[index]["matched_patterns"]),
                    "final_intent": final_intent,
                    "classifier_correct": predicted[index] == case["expected_intent"],
                    "final_correct": final_intent == case["expected_intent"],
                }
            )


def evaluate() -> dict[str, Any]:
    boundary = _load_jsonl(BOUNDARY_PATH)
    blind = _load_jsonl(BLIND_PATH)
    cases = boundary + blind
    with V5_DATASET_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        v5_rows = list(csv.DictReader(file))
    v5_texts = {row["text"].strip() for row in v5_rows}
    blind_overlap = v5_texts & {row["text"].strip() for row in blind}
    if blind_overlap:
        raise ValueError(f"Blind 48 데이터 누수가 있습니다: {sorted(blind_overlap)}")

    embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
    vectors = torch.tensor(
        embeddings.embed_documents([row["text"] for row in cases]),
        dtype=torch.float32,
    )
    boundary_count = len(boundary)
    independent_positions = {
        index
        for index, row in enumerate(boundary)
        if row["text"].strip() not in v5_texts
    }
    scopes = {
        "기존 60": list(range(boundary_count)),
        "독립 54": sorted(independent_positions),
        "Blind 48": list(range(boundary_count, len(cases))),
    }

    output: dict[str, Any] = {
        "labels": list(LABELS),
        "confusion_matrix_axis": "행=정답, 열=예측",
        "dataset": {
            "path": str(V5_DATASET_PATH),
            "count": len(v5_rows),
            "blind_exact_overlap": 0,
        },
        "scopes": {name: len(positions) for name, positions in scopes.items()},
        "models": {},
    }
    v5_prediction_data: tuple[list[str], list[float], list[list[float]]] | None = None
    for model_name, model_path in MODEL_PATHS.items():
        artifact = json.loads(model_path.read_text(encoding="utf-8"))
        predicted, confidence, probabilities = _predict(artifact, vectors)
        model_result: dict[str, Any] = {
            "model_version": artifact["model_version"],
            "validation": artifact["training"]["metrics"]["validation"],
            "classifier_only": {},
        }
        for scope_name, positions in scopes.items():
            expected = [cases[index]["expected_intent"] for index in positions]
            guesses = [predicted[index] for index in positions]
            model_result["classifier_only"][scope_name] = {
                "metrics": _metrics(expected, guesses),
                "errors": _error_rows(
                    cases,
                    positions,
                    predicted,
                    confidence,
                    probabilities,
                ),
            }
        output["models"][model_name] = model_result
        if model_name == "v5":
            v5_prediction_data = predicted, confidence, probabilities

    if v5_prediction_data is None:
        raise ValueError("v5 예측 결과가 없습니다.")
    predicted, confidence, probabilities = v5_prediction_data
    guards: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        guard = check_safety_guard(case["text"])
        guards.append(
            {
                "guard_triggered": guard.triggered,
                "guard_reason": guard.reason,
                "matched_patterns": guard.matched_patterns,
                "final_intent": "ignore" if guard.triggered else predicted[index],
            }
        )

    guard_result: dict[str, Any] = {}
    for scope_name, positions in scopes.items():
        expected = [cases[index]["expected_intent"] for index in positions]
        final_predictions = [guards[index]["final_intent"] for index in positions]
        guard_result[scope_name] = {
            "metrics": _metrics(expected, final_predictions),
            "errors": _error_rows(
                cases,
                positions,
                predicted,
                confidence,
                probabilities,
                guards,
            ),
            "guard_trigger_count": sum(
                guards[index]["guard_triggered"] for index in positions
            ),
        }
    output["models"]["v5"]["with_safety_guard"] = guard_result

    key_details: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if case["test_id"] not in KEY_BLIND_IDS:
            continue
        key_details.append(
            {
                "test_id": case["test_id"],
                "text": case["text"],
                "expected": case["expected_intent"],
                "classifier_intent": predicted[index],
                "classifier_probabilities": dict(
                    zip(LABELS, probabilities[index], strict=True)
                ),
                "confidence": confidence[index],
                "uncertain": confidence[index] < 0.55,
                **guards[index],
                "final_correct": guards[index]["final_intent"]
                == case["expected_intent"],
            }
        )
    output["key_blind_details"] = key_details

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "intent_v5_evaluation.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_predictions_csv(
        OUTPUT_DIR / "intent_v5_predictions.csv",
        cases,
        independent_positions,
        predicted,
        confidence,
        probabilities,
        guards,
        boundary_count,
    )
    return output


def main() -> int:
    try:
        result = evaluate()
        for model_name in ("v5",):
            print(model_name)
            for scope_name, data in result["models"][model_name][
                "classifier_only"
            ].items():
                metrics = data["metrics"]
                print(
                    f"  classifier {scope_name}: "
                    f"Accuracy={metrics['accuracy']:.4f}, "
                    f"Macro F1={metrics['macro_f1']:.4f}"
                )
        for scope_name, data in result["models"]["v5"][
            "with_safety_guard"
        ].items():
            metrics = data["metrics"]
            print(
                f"v5 guard {scope_name}: Accuracy={metrics['accuracy']:.4f}, "
                f"Macro F1={metrics['macro_f1']:.4f}"
            )
        print(f"저장: {OUTPUT_DIR}")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
