#!/usr/bin/env python3
"""HEAPY Intent Linear/Softmax 분류기를 새로 학습한다.

작성자: 김진우
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from langchain_huggingface import HuggingFaceEmbeddings

from model.classifier.script.intent_v6_utils import (
    CONFIDENCE_THRESHOLD,
    EMBED_DIMENSION,
    EMBED_MODEL,
    ID_TO_LABEL,
    LABELS,
    LABEL_TO_ID,
    ROOT,
    audit_data_integrity,
    classification_metrics,
    label_counts,
    load_checkpoint,
    load_dataset,
    prediction_rows,
    print_data_integrity,
    write_json,
    write_jsonl,
)


INTENT_LABELS = tuple(LABELS)
DEFAULT_TRAIN_DATA = ROOT / "classifier/data/HEAPY_intent_v6_train.jsonl"
DEFAULT_VALIDATION_DATA = (
    ROOT / "classifier/data/HEAPY_intent_v6_validation.jsonl"
)
DEFAULT_TEST_DATA = ROOT / "classifier/data/HEAPY_intent_v6_test.jsonl"
DEFAULT_BLIND_DATA = ROOT / "classifier/data/HEAPY_intent_v6_blind48.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "classifier/artifacts/intent-v6"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수를 입력하세요.")
    return parsed


def _probability(value: str) -> float:
    parsed = float(value)
    if not 0.0 < parsed < 1.0:
        raise argparse.ArgumentTypeError("0과 1 사이의 값을 입력하세요.")
    return parsed


def _load_dataset(path: Path) -> list[dict[str, str]]:
    """기존 테스트와 외부 호출을 위한 공통 로더 별칭."""
    return load_dataset(path)


def _classification_metrics(
    logits: torch.Tensor,
    labels: torch.Tensor,
) -> dict[str, Any]:
    """기존 테스트와 외부 호출을 위한 metric 별칭."""
    return classification_metrics(logits, labels)


def _set_seed(seed: int) -> None:
    """Python·PyTorch·CUDA 난수 시드를 고정한다."""
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _embed_splits(
    datasets: dict[str, list[dict[str, str]]],
    device: torch.device,
) -> dict[str, torch.Tensor]:
    """Frozen Sentence Transformer로 Train·Validation·Test를 임베딩한다."""
    print(f"임베딩 모델 로드: {EMBED_MODEL} ({device.type})")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": device.type},
    )
    result: dict[str, torch.Tensor] = {}
    for split_name, examples in datasets.items():
        vectors = embeddings.embed_documents(
            [example["text"] for example in examples]
        )
        if any(len(vector) != EMBED_DIMENSION for vector in vectors):
            raise ValueError(
                f"{split_name} 임베딩은 모두 "
                f"{EMBED_DIMENSION}차원이어야 합니다."
            )
        result[split_name] = torch.tensor(
            vectors,
            dtype=torch.float32,
            device=device,
        )
    return result


def _targets(
    examples: list[dict[str, str]],
    device: torch.device,
) -> torch.Tensor:
    return torch.tensor(
        [LABEL_TO_ID[example["label"]] for example in examples],
        dtype=torch.long,
        device=device,
    )


def _evaluate(
    model: torch.nn.Linear,
    features: torch.Tensor,
    targets: torch.Tensor,
    loss_function: torch.nn.Module,
) -> tuple[dict[str, Any], torch.Tensor]:
    """현재 모델의 loss와 분류 지표를 계산한다."""
    model.eval()
    with torch.no_grad():
        logits = model(features)
        loss = float(loss_function(logits, targets).item())
    return classification_metrics(logits, targets, loss), logits


def _model_state(model: torch.nn.Linear) -> dict[str, torch.Tensor]:
    """Linear Layer 가중치를 CPU에 복사한다."""
    return {
        key: value.detach().cpu().clone()
        for key, value in model.state_dict().items()
    }


def _checkpoint_payload(
    state_dict: dict[str, torch.Tensor],
    model_version: str,
    checkpoint_kind: str,
    training: dict[str, Any],
) -> dict[str, Any]:
    """서버의 LinearIntentClassifier와 호환되는 JSON을 만든다."""
    return {
        "schema_version": 1,
        "model_type": "linear_softmax",
        "model_version": model_version,
        "embedding_model": EMBED_MODEL,
        "embedding_dimension": EMBED_DIMENSION,
        "labels": list(LABELS),
        "weights": state_dict["weight"].tolist(),
        "bias": state_dict["bias"].tolist(),
        "checkpoint_kind": checkpoint_kind,
        "confidence_threshold": training["confidence_threshold"],
        "training": training,
    }


def _dataset_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def train(args: argparse.Namespace) -> dict[str, Any]:
    """지정된 고정 split으로 학습하고 best·final 체크포인트를 저장한다."""
    paths = {
        "train": args.train_data.resolve(),
        "validation": args.validation_data.resolve(),
        "test": args.test_data.resolve(),
        "blind": args.blind_data.resolve(),
    }
    datasets = {name: load_dataset(path) for name, path in paths.items()}
    integrity = audit_data_integrity(datasets, paths)
    print_data_integrity(integrity)

    for split_name in ("train", "validation", "test"):
        missing = [
            label
            for label, count in label_counts(datasets[split_name]).items()
            if count == 0
        ]
        if missing:
            raise ValueError(
                f"{split_name}에 데이터가 없는 label이 있습니다: {missing}"
            )

    _set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Linear Layer 학습 device: {device.type}")

    learning_datasets = {
        name: datasets[name]
        for name in ("train", "validation", "test")
    }
    features = _embed_splits(learning_datasets, device)
    targets = {
        name: _targets(examples, device)
        for name, examples in learning_datasets.items()
    }

    model = torch.nn.Linear(EMBED_DIMENSION, len(LABELS)).to(device)
    if model.out_features != len(LABELS):
        raise ValueError("모델 출력 차원은 4여야 합니다.")
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    loss_function = torch.nn.CrossEntropyLoss()

    best_macro_f1 = -1.0
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    epochs_without_improvement = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        train_logits = model(features["train"])
        train_loss = loss_function(train_logits, targets["train"])
        train_loss.backward()
        optimizer.step()

        validation_metrics, _ = _evaluate(
            model,
            features["validation"],
            targets["validation"],
            loss_function,
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": float(train_loss.item()),
                "validation_loss": validation_metrics["loss"],
                "validation_macro_f1": validation_metrics["macro_f1"],
            }
        )

        if validation_metrics["macro_f1"] > best_macro_f1 + 1e-12:
            best_macro_f1 = validation_metrics["macro_f1"]
            best_epoch = epoch
            best_state = _model_state(model)
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(
                    f"Early stopping: epoch={epoch}, "
                    f"best validation Macro F1={best_macro_f1:.4f}"
                )
                break

    if best_state is None:
        raise RuntimeError("best checkpoint를 생성하지 못했습니다.")
    final_state = _model_state(model)
    final_validation, _ = _evaluate(
        model,
        features["validation"],
        targets["validation"],
        loss_function,
    )

    model.load_state_dict({key: value.to(device) for key, value in best_state.items()})
    best_train, _ = _evaluate(
        model,
        features["train"],
        targets["train"],
        loss_function,
    )
    best_validation, validation_logits = _evaluate(
        model,
        features["validation"],
        targets["validation"],
        loss_function,
    )
    best_test, test_logits = _evaluate(
        model,
        features["test"],
        targets["test"],
        loss_function,
    )

    output_dir = args.output_dir.resolve()
    created_at = datetime.now(UTC).isoformat()
    dataset_sha256 = _dataset_hash([paths["train"], paths["validation"]])
    model_version = f"{args.model_version_prefix}-{dataset_sha256[:12]}"
    training_config = {
        "created_at": created_at,
        "random_seed": args.seed,
        "epochs_requested": args.epochs,
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "best_model_selection": "validation_macro_f1",
        "early_stopping_patience": args.patience,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "optimizer": "AdamW",
        "scheduler": None,
        "loss_function": "CrossEntropyLoss",
        "batch_strategy": "full_batch",
        "linear_initialization": "random",
        "parent_checkpoint": None,
        "sentence_transformer_frozen": True,
        "device": device.type,
        "confidence_threshold": args.confidence_threshold,
        "dataset_sha256": dataset_sha256,
        "data_files": {name: path.name for name, path in paths.items()},
        "split_counts": {
            name: len(examples) for name, examples in datasets.items()
        },
        "label_counts": {
            name: label_counts(examples)
            for name, examples in datasets.items()
        },
        "merged_820_used_for_training": False,
        "blind_used_for_training_or_selection": False,
        "history": history,
        "train_result": best_train,
        "validation_result": best_validation,
        "test_result": best_test,
        "final_validation_result": final_validation,
    }

    best_path = output_dir / "best_model.json"
    final_path = output_dir / "final_model.json"
    metadata = {
        "schema_version": 1,
        "model_version": model_version,
        "status": "candidate",
        "created_at": created_at,
        "embedding_model": EMBED_MODEL,
        "embedding_dimension": EMBED_DIMENSION,
        "labels": list(LABELS),
        "label_to_id": LABEL_TO_ID,
        "id_to_label": {str(key): value for key, value in ID_TO_LABEL.items()},
        "confidence_threshold": args.confidence_threshold,
        "training_config": {
            key: value
            for key, value in training_config.items()
            if key not in {"history", "train_result", "validation_result", "test_result"}
        },
        "data_integrity": integrity,
        "train_result": best_train,
        "validation_result": best_validation,
        "test_result": best_test,
        "checkpoint_paths": {
            "best": best_path.name,
            "final": final_path.name,
        },
    }
    write_json(
        best_path,
        _checkpoint_payload(
            best_state,
            model_version,
            "best",
            training_config,
        ),
    )
    write_json(
        final_path,
        _checkpoint_payload(
            final_state,
            f"{model_version}-final",
            "final",
            training_config,
        ),
    )
    write_json(
        output_dir / "label_mapping.json",
        {
            "labels": LABELS,
            "label_to_id": LABEL_TO_ID,
            "id_to_label": {str(key): value for key, value in ID_TO_LABEL.items()},
        },
    )
    write_json(output_dir / "training_config.json", training_config)
    write_json(output_dir / "metadata.json", metadata)
    write_jsonl(
        output_dir / "validation_predictions.jsonl",
        prediction_rows(
            datasets["validation"],
            validation_logits,
            args.confidence_threshold,
        ),
    )
    write_jsonl(
        output_dir / "test_predictions.jsonl",
        prediction_rows(
            datasets["test"],
            test_logits,
            args.confidence_threshold,
        ),
    )

    # 저장 직후 재로딩 검증으로 손상된 체크포인트를 차단한다.
    load_checkpoint(best_path)
    load_checkpoint(final_path)

    print("\n[학습 결과]")
    for split_name, metrics in (
        ("Train", best_train),
        ("Validation", best_validation),
        ("Test", best_test),
    ):
        print(
            f"{split_name}: loss={metrics['loss']:.4f}, "
            f"accuracy={metrics['accuracy']:.4f}, "
            f"macro_f1={metrics['macro_f1']:.4f}"
        )
        print(f"  confusion_matrix={metrics['confusion_matrix']}")
    print(f"best epoch: {best_epoch}")
    print(f"best checkpoint: {best_path}")
    print(f"final checkpoint: {final_path}")
    print(f"model version: {model_version}")
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-data", type=Path, default=DEFAULT_TRAIN_DATA)
    parser.add_argument(
        "--validation-data",
        type=Path,
        default=DEFAULT_VALIDATION_DATA,
    )
    parser.add_argument("--test-data", type=Path, default=DEFAULT_TEST_DATA)
    parser.add_argument("--blind-data", type=Path, default=DEFAULT_BLIND_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-version-prefix", default="intent-v6")
    parser.add_argument("--epochs", type=_positive_int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.02)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--patience", type=_positive_int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--confidence-threshold",
        type=_probability,
        default=CONFIDENCE_THRESHOLD,
    )
    return parser


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        train(build_parser().parse_args())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
