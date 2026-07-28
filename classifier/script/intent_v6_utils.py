"""HEAPY Intent v6 학습·평가 공통 도구.

작성자: 김진우
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

import torch


ROOT = Path(__file__).resolve().parents[2]
EMBED_MODEL = "jhgan/ko-sroberta-multitask"
EMBED_DIMENSION = 768
LABELS = [
    "simple_lookup",
    "comprehensive",
    "general_chat",
    "ignore",
]
LABEL_TO_ID = {label: idx for idx, label in enumerate(LABELS)}
ID_TO_LABEL = {idx: label for label, idx in LABEL_TO_ID.items()}
CONFIDENCE_THRESHOLD = 0.55


def load_dataset(path: Path) -> list[dict[str, str]]:
    """UTF-8 JSONL 데이터를 행 단위로 읽고 필수 필드를 검증한다."""
    if path.suffix.lower() == ".csv":
        return _load_csv_dataset(path)
    if path.suffix.lower() != ".jsonl":
        raise ValueError(f"JSONL 또는 CSV 파일만 지원합니다: {path}")

    examples: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                item: Any = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"잘못된 JSON입니다: {path}:{line_number} "
                    f"({error.msg})"
                ) from error
            if not isinstance(item, dict):
                raise ValueError(
                    f"JSON 객체가 아닙니다: {path}:{line_number}"
                )
            if "text" not in item:
                raise ValueError(f"text 필드가 없습니다: {path}:{line_number}")
            if "label" not in item:
                raise ValueError(f"label 필드가 없습니다: {path}:{line_number}")

            text = str(item["text"]).strip()
            label = str(item["label"]).strip()
            if not text:
                raise ValueError(f"빈 text입니다: {path}:{line_number}")
            if label not in LABEL_TO_ID:
                raise ValueError(
                    f"허용하지 않는 label입니다: {label} "
                    f"({path}:{line_number})"
                )
            examples.append({"text": text, "label": label})

    if not examples:
        raise ValueError(f"데이터가 없습니다: {path}")
    return examples


def _load_csv_dataset(path: Path) -> list[dict[str, str]]:
    """기존 실험 재현을 위한 CSV 호환 로더."""
    examples: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row_number, row in enumerate(csv.DictReader(file), start=2):
            if "text" not in row:
                raise ValueError(f"text 필드가 없습니다: {path}:{row_number}")
            if "label" not in row and "intent" not in row:
                raise ValueError(f"label 필드가 없습니다: {path}:{row_number}")
            text = str(row.get("text", "")).strip()
            label = str(row.get("label") or row.get("intent") or "").strip()
            if not text:
                raise ValueError(f"빈 text입니다: {path}:{row_number}")
            if label not in LABEL_TO_ID:
                raise ValueError(
                    f"허용하지 않는 label입니다: {label} "
                    f"({path}:{row_number})"
                )
            examples.append({"text": text, "label": label})
    if not examples:
        raise ValueError(f"데이터가 없습니다: {path}")
    return examples


def normalized_text(text: str) -> str:
    """앞뒤·연속 공백을 정규화해 문장 누수를 검사한다."""
    return re.sub(r"\s+", " ", text.strip())


def label_counts(examples: list[dict[str, str]]) -> dict[str, int]:
    """고정된 라벨 순서로 건수를 반환한다."""
    counts = Counter(example["label"] for example in examples)
    return {label: counts[label] for label in LABELS}


def audit_data_integrity(
    datasets: dict[str, list[dict[str, str]]],
    paths: dict[str, Path],
) -> dict[str, Any]:
    """split 내부 중복과 split 간 문장 누수를 검사한다."""
    split_reports: dict[str, Any] = {}
    warnings: list[str] = []
    for split_name, examples in datasets.items():
        texts = [example["text"] for example in examples]
        normalized = [normalized_text(text) for text in texts]
        exact_duplicates = len(texts) - len(set(texts))
        normalized_duplicates = len(normalized) - len(set(normalized))
        split_reports[split_name] = {
            "file": paths[split_name].name,
            "count": len(examples),
            "label_counts": label_counts(examples),
            "empty_text_count": 0,
            "invalid_label_count": 0,
            "exact_duplicate_count": exact_duplicates,
            "normalized_duplicate_count": normalized_duplicates,
        }
        if exact_duplicates:
            warnings.append(
                f"{split_name} 내부에 완전히 동일한 문장이 "
                f"{exact_duplicates}건 있습니다."
            )
        elif normalized_duplicates:
            warnings.append(
                f"{split_name} 내부에 공백 정규화 후 동일한 "
                f"문장이 {normalized_duplicates}건 있습니다."
            )

    overlap_reports: dict[str, Any] = {}
    for left, right in combinations(datasets, 2):
        left_exact = {item["text"] for item in datasets[left]}
        right_exact = {item["text"] for item in datasets[right]}
        left_normalized = {normalized_text(item["text"]) for item in datasets[left]}
        right_normalized = {
            normalized_text(item["text"]) for item in datasets[right]
        }
        exact_count = len(left_exact & right_exact)
        normalized_count = len(left_normalized & right_normalized)
        key = f"{left}__{right}"
        overlap_reports[key] = {
            "exact_text_overlap_count": exact_count,
            "normalized_text_overlap_count": normalized_count,
        }
        if exact_count:
            warnings.append(
                f"{left}–{right} 간 완전히 동일한 문장이 "
                f"{exact_count}건 있습니다."
            )
        elif normalized_count:
            warnings.append(
                f"{left}–{right} 간 공백 정규화 후 동일한 "
                f"문장이 {normalized_count}건 있습니다."
            )

    return {
        "splits": split_reports,
        "overlaps": overlap_reports,
        "warnings": warnings,
    }


def print_data_integrity(report: dict[str, Any]) -> None:
    """학습 전 무결성 검사 결과와 누수 경고를 출력한다."""
    print("\n[데이터 무결성 검사]")
    for split_name, split in report["splits"].items():
        print(
            f"{split_name}: {split['count']}건, "
            f"빈 text={split['empty_text_count']}, "
            f"잘못된 label={split['invalid_label_count']}, "
            f"내부 중복={split['exact_duplicate_count']}"
        )
        for label in LABELS:
            print(f"  {label}: {split['label_counts'][label]}건")
    print("split 간 중복:")
    for pair, overlap in report["overlaps"].items():
        print(
            f"  {pair}: exact={overlap['exact_text_overlap_count']}, "
            f"normalized={overlap['normalized_text_overlap_count']}"
        )
    for warning in report["warnings"]:
        print(f"경고: {warning}")


def classification_metrics_from_predictions(
    true_ids: list[int],
    predicted_ids: list[int],
    loss: float | None = None,
) -> dict[str, Any]:
    """Macro·클래스별 지표와 confusion matrix를 계산한다."""
    if len(true_ids) != len(predicted_ids):
        raise ValueError("정답과 예측 개수가 다릅니다.")
    if not true_ids:
        raise ValueError("평가 데이터가 없습니다.")

    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for true_id, predicted_id in zip(true_ids, predicted_ids, strict=True):
        matrix[true_id][predicted_id] += 1

    per_class: dict[str, Any] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    f1_scores: list[float] = []
    for index, label in enumerate(LABELS):
        true_positive = matrix[index][index]
        predicted_count = sum(row[index] for row in matrix)
        support = sum(matrix[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
        per_class[label] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    correct = sum(matrix[index][index] for index in range(len(LABELS)))
    return {
        "count": len(true_ids),
        "loss": loss,
        "accuracy": correct / len(true_ids),
        "macro_precision": sum(precisions) / len(precisions),
        "macro_recall": sum(recalls) / len(recalls),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "per_class": per_class,
        "confusion_matrix": matrix,
        "confusion_matrix_labels": list(LABELS),
    }


def classification_metrics(
    logits: torch.Tensor,
    targets: torch.Tensor,
    loss: float | None = None,
) -> dict[str, Any]:
    """logits에서 예측을 구해 분류 지표를 계산한다."""
    predicted_ids = logits.argmax(dim=1).detach().cpu().tolist()
    true_ids = targets.detach().cpu().tolist()
    return classification_metrics_from_predictions(true_ids, predicted_ids, loss)


def prediction_rows(
    examples: list[dict[str, str]],
    logits: torch.Tensor,
    threshold: float,
) -> list[dict[str, Any]]:
    """문장별 정답·예측·confidence·uncertain을 생성한다."""
    probabilities = torch.softmax(logits, dim=1).detach().cpu()
    rows: list[dict[str, Any]] = []
    for example, probability in zip(examples, probabilities, strict=True):
        confidence, predicted_id = probability.max(dim=0)
        confidence_value = float(confidence.item())
        rows.append(
            {
                "text": example["text"],
                "true_label": example["label"],
                "predicted_label": ID_TO_LABEL[int(predicted_id.item())],
                "confidence": confidence_value,
                "uncertain": confidence_value < threshold,
                "probabilities": {
                    label: float(probability[index].item())
                    for index, label in enumerate(LABELS)
                },
            }
        )
    return rows


def write_json(path: Path, payload: Any) -> None:
    """JSON 산출물을 UTF-8로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """문장별 평가 결과를 UTF-8 JSONL로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_checkpoint(path: Path) -> dict[str, Any]:
    """v6 체크포인트를 읽고 구조와 라벨 순서를 검증한다."""
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"체크포인트가 JSON 객체가 아닙니다: {path}")
    if payload.get("labels") != LABELS:
        raise ValueError(f"체크포인트 라벨 순서가 다릅니다: {path}")
    weights = payload.get("weights")
    bias = payload.get("bias")
    if not isinstance(weights, list) or len(weights) != len(LABELS):
        raise ValueError(f"체크포인트 weight가 올바르지 않습니다: {path}")
    if any(not isinstance(row, list) or len(row) != EMBED_DIMENSION for row in weights):
        raise ValueError(f"체크포인트 weight 차원이 다릅니다: {path}")
    if not isinstance(bias, list) or len(bias) != len(LABELS):
        raise ValueError(f"체크포인트 bias가 올바르지 않습니다: {path}")
    return payload


def logits_from_checkpoint(
    features: torch.Tensor,
    checkpoint: dict[str, Any],
) -> torch.Tensor:
    """저장된 Linear weight와 bias로 logits을 계산한다."""
    weights = torch.tensor(checkpoint["weights"], dtype=torch.float32)
    bias = torch.tensor(checkpoint["bias"], dtype=torch.float32)
    return features.cpu() @ weights.transpose(0, 1) + bias

