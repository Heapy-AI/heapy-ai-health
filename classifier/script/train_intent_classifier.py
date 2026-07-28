#!/usr/bin/env python3
"""동결된 문장 임베딩 위에 Linear/Softmax intent 분류기를 학습한다.

작성자: 김진우
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from langchain_huggingface import HuggingFaceEmbeddings


ROOT = Path(__file__).resolve().parents[2]
EMBED_MODEL = "jhgan/ko-sroberta-multitask"
EMBED_DIMENSION = 768
INTENT_LABELS = (
    "simple_lookup",
    "comprehensive",
    "general_chat",
    "ignore",
)
DEFAULT_DATASET = (
    ROOT / "classifier" / "data" / "HEAPY_intent_dataset_v3_500.csv"
)
DEFAULT_OUTPUT = (
    ROOT / "classifier" / "artifacts" / "intent_linear_v5_candidate.json"
)
DEFAULT_MINIMUM_PER_CLASS = 20
TYPO_SOURCE = "curated_typo"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수를 입력하세요.")
    return parsed


def _read_dataset_rows(path: Path) -> list[dict[str, Any]]:
    """CSV 또는 JSONL 학습 데이터를 공통 객체 목록으로 읽는다."""
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = [dict(row) for row in csv.DictReader(file)]
        for row in rows:
            row["intent"] = row.get("intent") or row.get("label")
        return rows
    if path.suffix.lower() != ".jsonl":
        raise ValueError("학습 데이터는 CSV 또는 JSONL 형식이어야 합니다.")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            item: Any = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"JSON 객체가 아닙니다: {path}:{line_number}")
            rows.append(item)
    return rows


def _load_dataset(path: Path) -> list[dict[str, str]]:
    """학습 데이터를 읽고 라벨·중복을 검증한다."""
    examples: list[dict[str, str]] = []
    seen_texts: set[str] = set()

    for row_number, item in enumerate(_read_dataset_rows(path), start=2):
        text = str(item.get("text", "")).strip()
        intent = str(item.get("intent", "")).strip()
        if not text:
            raise ValueError(f"빈 text입니다: {path}:{row_number}")
        if intent not in INTENT_LABELS:
            raise ValueError(
                f"지원하지 않는 intent입니다: {intent} "
                f"({path}:{row_number})"
            )
        if text in seen_texts:
            raise ValueError(f"중복 학습 문장입니다: {text}")

        seen_texts.add(text)
        source = str(item.get("source", "curated")).strip() or "curated"
        group_id = str(item.get("group_id", text)).strip() or text
        examples.append(
            {
                "text": text,
                "intent": intent,
                "source": source,
                "group_id": group_id,
            }
        )

    if not examples:
        raise ValueError(f"학습 데이터가 없습니다: {path}")
    return examples


def _validate_class_counts(
    examples: list[dict[str, str]],
    minimum_per_class: int,
    allow_small_dataset: bool,
) -> Counter[str]:
    """라벨 누락과 운영 학습에 부족한 표본 수를 차단한다."""
    counts = Counter(example["intent"] for example in examples)
    missing = [label for label in INTENT_LABELS if counts[label] == 0]
    if missing:
        raise ValueError(f"학습 예시가 없는 intent가 있습니다: {missing}")

    insufficient = {
        label: counts[label]
        for label in INTENT_LABELS
        if counts[label] < minimum_per_class
    }
    if insufficient and not allow_small_dataset:
        raise ValueError(
            f"intent별 학습 예시가 부족합니다: {insufficient}. "
            f"클래스당 최소 {minimum_per_class}개가 필요합니다. "
            "구조 검증만 할 때는 --allow-small-dataset을 사용하세요."
        )
    return counts


def _split_indices(
    examples: list[dict[str, str]],
    seed: int,
    use_validation: bool,
) -> tuple[list[int], list[int], list[int], list[int]]:
    """라벨·그룹을 보존해 학습·검증·테스트·오타 평가셋을 나눈다."""
    random_generator = random.Random(seed)
    grouped: dict[str, list[int]] = {}
    for index, example in enumerate(examples):
        grouped.setdefault(example["group_id"], []).append(index)

    challenge_group_ids = {
        example["group_id"]
        for example in examples
        if example["source"] == TYPO_SOURCE
    }
    challenge_indices = [
        index
        for group_id in challenge_group_ids
        for index in grouped[group_id]
    ]
    eligible_groups = [
        indices
        for group_id, indices in grouped.items()
        if group_id not in challenge_group_ids
    ]

    if use_validation:
        eligible_indices = [index for group in eligible_groups for index in group]
        intent_counts = Counter(examples[index]["intent"] for index in eligible_indices)
        targets = {
            label: max(1, round(intent_counts[label] * 0.1))
            for label in INTENT_LABELS
        }
        validation_groups, remaining_groups = _select_groups_for_targets(
            eligible_groups,
            examples,
            targets,
            random_generator,
        )
        test_groups, train_groups = _select_groups_for_targets(
            remaining_groups,
            examples,
            targets,
            random_generator,
        )
    else:
        train_groups = eligible_groups
        validation_groups = []
        test_groups = []

    train_indices = [index for group in train_groups for index in group]
    validation_indices = [
        index for group in validation_groups for index in group
    ]
    test_indices = [index for group in test_groups for index in group]

    random_generator.shuffle(train_indices)
    random_generator.shuffle(validation_indices)
    random_generator.shuffle(test_indices)
    random_generator.shuffle(challenge_indices)
    return train_indices, validation_indices, test_indices, challenge_indices


def _select_groups_for_targets(
    groups: list[list[int]],
    examples: list[dict[str, str]],
    targets: dict[str, int],
    random_generator: random.Random,
) -> tuple[list[list[int]], list[list[int]]]:
    """라벨별 목표 수를 만족하도록 그룹 전체를 원자적으로 선택한다."""
    remaining = list(groups)
    random_generator.shuffle(remaining)
    selected: list[list[int]] = []
    selected_counts: Counter[str] = Counter()

    while any(selected_counts[label] < targets[label] for label in INTENT_LABELS):
        deficits = {
            label: max(0, targets[label] - selected_counts[label])
            for label in INTENT_LABELS
        }
        best_position = -1
        best_coverage = 0
        for position, group in enumerate(remaining):
            group_counts = Counter(examples[index]["intent"] for index in group)
            coverage = sum(
                min(deficits[label], group_counts[label])
                for label in INTENT_LABELS
            )
            if coverage > best_coverage:
                best_position = position
                best_coverage = coverage

        if best_position < 0:
            missing = {
                label: deficits[label]
                for label in INTENT_LABELS
                if deficits[label] > 0
            }
            raise ValueError(f"데이터 분할 목표를 충족할 수 없습니다: {missing}")

        group = remaining.pop(best_position)
        selected.append(group)
        selected_counts.update(examples[index]["intent"] for index in group)

    return selected, remaining


def _accuracy(logits: torch.Tensor, labels: torch.Tensor) -> float:
    predictions = logits.argmax(dim=1)
    return float((predictions == labels).float().mean().item())


def _classification_metrics(
    logits: torch.Tensor,
    labels: torch.Tensor,
) -> dict[str, Any] | None:
    """정확도, Macro 지표와 confusion matrix를 계산한다."""
    if labels.numel() == 0:
        return None

    predictions = logits.argmax(dim=1)
    confusion_matrix = [
        [0 for _ in INTENT_LABELS]
        for _ in INTENT_LABELS
    ]
    for expected, predicted in zip(
        labels.tolist(),
        predictions.tolist(),
        strict=True,
    ):
        confusion_matrix[expected][predicted] += 1

    precisions: list[float] = []
    recalls: list[float] = []
    f1_scores: list[float] = []
    for index in range(len(INTENT_LABELS)):
        true_positive = confusion_matrix[index][index]
        predicted_count = sum(row[index] for row in confusion_matrix)
        expected_count = sum(confusion_matrix[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / expected_count if expected_count else 0.0
        f1_score = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1_score)

    return {
        "example_count": int(labels.numel()),
        "accuracy": _accuracy(logits, labels),
        "macro_precision": sum(precisions) / len(precisions),
        "macro_recall": sum(recalls) / len(recalls),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "confusion_matrix": confusion_matrix,
    }


def train(args: argparse.Namespace) -> None:
    """학습 데이터 검증, 임베딩, 선형 분류기 학습, artifact 저장을 수행한다."""
    dataset_path = args.dataset.resolve()
    output_path = args.output.resolve()
    examples = _load_dataset(dataset_path)
    counts = _validate_class_counts(
        examples,
        args.minimum_per_class,
        args.allow_small_dataset,
    )
    use_validation = not args.allow_small_dataset

    print(f"학습 데이터: {dataset_path}")
    print(f"전체 예시: {len(examples)}건")
    for label in INTENT_LABELS:
        print(f"  {label}: {counts[label]}건")

    print(f"임베딩 모델 로드 중: {EMBED_MODEL}")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectors = embeddings.embed_documents([example["text"] for example in examples])
    if any(len(vector) != EMBED_DIMENSION for vector in vectors):
        raise ValueError(f"모든 임베딩은 {EMBED_DIMENSION}차원이어야 합니다.")

    label_to_index = {label: index for index, label in enumerate(INTENT_LABELS)}
    features = torch.tensor(vectors, dtype=torch.float32)
    targets = torch.tensor(
        [label_to_index[example["intent"]] for example in examples],
        dtype=torch.long,
    )
    (
        train_indices,
        validation_indices,
        test_indices,
        challenge_indices,
    ) = _split_indices(
        examples,
        args.seed,
        use_validation,
    )
    print(
        "데이터 분할: "
        f"train={len(train_indices)}, "
        f"validation={len(validation_indices)}, "
        f"test={len(test_indices)}, "
        f"typo_challenge={len(challenge_indices)}"
    )

    torch.manual_seed(args.seed)
    model = torch.nn.Linear(EMBED_DIMENSION, len(INTENT_LABELS))
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    loss_function = torch.nn.CrossEntropyLoss()

    train_features = features[train_indices]
    train_targets = targets[train_indices]
    best_epoch = args.epochs
    best_validation_loss = float("inf")
    best_weights: torch.Tensor | None = None
    best_bias: torch.Tensor | None = None
    epochs_without_improvement = 0
    loss_curve: list[dict[str, float | int | None]] = []
    for epoch in range(1, args.epochs + 1):
        optimizer.zero_grad()
        loss = loss_function(model(train_features), train_targets)
        loss.backward()
        optimizer.step()

        train_loss = float(loss.item())
        if not validation_indices:
            loss_curve.append(
                {"epoch": epoch, "train": train_loss, "validation": None}
            )
            continue
        with torch.no_grad():
            validation_loss = float(
                loss_function(
                    model(features[validation_indices]),
                    targets[validation_indices],
                ).item()
            )
        loss_curve.append(
            {
                "epoch": epoch,
                "train": train_loss,
                "validation": validation_loss,
            }
        )
        if validation_loss < best_validation_loss - 1e-8:
            best_validation_loss = validation_loss
            best_epoch = epoch
            best_weights = model.weight.detach().clone()
            best_bias = model.bias.detach().clone()
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                break

    if best_weights is not None and best_bias is not None:
        with torch.no_grad():
            model.weight.copy_(best_weights)
            model.bias.copy_(best_bias)

    model.eval()
    with torch.no_grad():
        def metrics_for(indices: list[int]) -> dict[str, Any] | None:
            if not indices:
                return None
            return _classification_metrics(
                model(features[indices]),
                targets[indices],
            )

        train_metrics = metrics_for(train_indices)
        validation_metrics = metrics_for(validation_indices)
        test_metrics = metrics_for(test_indices)
        challenge_metrics = metrics_for(challenge_indices)

    if train_metrics is None:
        raise ValueError("학습 데이터 분할 결과가 비어 있습니다.")

    dataset_bytes = dataset_path.read_bytes()
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    model_version = f"intent-linear-{dataset_hash[:12]}"
    weights = model.weight.detach().cpu().tolist()
    bias = model.bias.detach().cpu().tolist()

    payload = {
        "schema_version": 1,
        "model_type": "linear_softmax",
        "model_version": model_version,
        "embedding_model": EMBED_MODEL,
        "embedding_dimension": EMBED_DIMENSION,
        "labels": list(INTENT_LABELS),
        "weights": weights,
        "bias": bias,
        "training": {
            "created_at": datetime.now(UTC).isoformat(),
            "dataset_sha256": dataset_hash,
            "example_count": len(examples),
            "class_counts": dict(counts),
            "source_counts": dict(
                Counter(example["source"] for example in examples)
            ),
            "split_counts": {
                "train": len(train_indices),
                "validation": len(validation_indices),
                "test": len(test_indices),
                "typo_challenge": len(challenge_indices),
            },
            "train_accuracy": train_metrics["accuracy"],
            "validation_accuracy": (
                validation_metrics["accuracy"]
                if validation_metrics is not None
                else None
            ),
            "test_accuracy": (
                test_metrics["accuracy"]
                if test_metrics is not None
                else None
            ),
            "typo_challenge_accuracy": (
                challenge_metrics["accuracy"]
                if challenge_metrics is not None
                else None
            ),
            "metrics": {
                "train": train_metrics,
                "validation": validation_metrics,
                "test": test_metrics,
                "typo_challenge": challenge_metrics,
            },
            "best_epoch": best_epoch,
            "seed": args.seed,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "optimizer": "AdamW",
            "scheduler": None,
            "loss_function": "CrossEntropyLoss",
            "batch_strategy": "full_batch",
            "linear_initialization": "random",
            "parent_checkpoint": None,
            "sentence_transformer_frozen": True,
            "loss_curve": loss_curve,
            "prototype": args.allow_small_dataset,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    for name, metrics in (
        ("학습", train_metrics),
        ("검증", validation_metrics),
        ("테스트", test_metrics),
        ("오타 challenge", challenge_metrics),
    ):
        if metrics is None:
            print(f"{name} 평가: 없음")
            continue
        print(
            f"{name} 정확도={metrics['accuracy']:.4f}, "
            f"Macro F1={metrics['macro_f1']:.4f}, "
            f"Macro Precision={metrics['macro_precision']:.4f}, "
            f"Macro Recall={metrics['macro_recall']:.4f}"
        )
        print(f"{name} Confusion Matrix={metrics['confusion_matrix']}")
    print(f"Loss Curve epoch 수: {len(loss_curve)}")
    print(f"최적 epoch: {best_epoch}")
    print(f"모델 저장: {output_path}")
    print(f"모델 버전: {model_version}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-per-class", type=_positive_int, default=20)
    parser.add_argument("--epochs", type=_positive_int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.02)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--patience", type=_positive_int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--allow-small-dataset",
        action="store_true",
        help="운영 품질 검증 없이 소규모 fixture로 구조만 시험",
    )
    return parser


def main() -> int:
    try:
        train(build_parser().parse_args())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
