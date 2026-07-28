#!/usr/bin/env python3
"""Intent v5 학습·외부 평가·Safety Guard 결과 보고서를 생성한다.

작성자: 김진우
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT_PATH = ROOT / "classifier/artifacts/intent_linear_v5_candidate.json"
EVALUATION_PATH = (
    ROOT / "classifier/evaluation/intent_v5/intent_v5_evaluation.json"
)
OUTPUT_DIR = ROOT / "classifier/evaluation/intent_v5"
REPORT_PATH = OUTPUT_DIR / "intent_v5_training_report.md"


def _polyline(
    values: list[float],
    width: int,
    height: int,
    padding: int,
    maximum: float,
) -> str:
    usable_width = width - 2 * padding
    usable_height = height - 2 * padding
    divisor = max(1, len(values) - 1)
    return " ".join(
        f"{padding + usable_width * index / divisor:.1f},"
        f"{height - padding - usable_height * value / maximum:.1f}"
        for index, value in enumerate(values)
    )


def _write_loss_curve(path: Path, curve: list[dict[str, Any]]) -> None:
    """학습·검증 loss를 외부 의존성 없는 SVG로 저장한다."""
    width, height, padding = 900, 480, 60
    train = [float(point["train"]) for point in curve]
    validation = [float(point["validation"]) for point in curve]
    maximum = max(train + validation) * 1.05
    train_points = _polyline(train, width, height, padding, maximum)
    validation_points = _polyline(validation, width, height, padding, maximum)
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="450" y="28" text-anchor="middle" font-size="20" font-family="sans-serif">Intent v5 Loss Curve</text>
  <line x1="60" y1="420" x2="840" y2="420" stroke="#333"/>
  <line x1="60" y1="60" x2="60" y2="420" stroke="#333"/>
  <polyline points="{train_points}" fill="none" stroke="#2563eb" stroke-width="3"/>
  <polyline points="{validation_points}" fill="none" stroke="#dc2626" stroke-width="3"/>
  <text x="690" y="55" font-size="14" fill="#2563eb">Train Loss</text>
  <text x="790" y="55" font-size="14" fill="#dc2626">Validation Loss</text>
  <text x="450" y="465" text-anchor="middle" font-size="14">Epoch</text>
  <text x="18" y="240" text-anchor="middle" font-size="14" transform="rotate(-90 18 240)">Loss</text>
</svg>
""",
        encoding="utf-8",
    )


def _format_matrix(matrix: list[list[int]]) -> str:
    return "`" + json.dumps(matrix, ensure_ascii=False, separators=(",", ":")) + "`"


def _probabilities(probabilities: dict[str, float]) -> str:
    return ", ".join(
        f"{label}={probabilities[label]:.4f}"
        for label in (
            "simple_lookup",
            "comprehensive",
            "general_chat",
            "ignore",
        )
    )


def _append_error_table(
    lines: list[str],
    title: str,
    errors: list[dict[str, Any]],
) -> None:
    lines.extend(
        [
            f"### {title}",
            "",
            "| ID | 문장 | 정답 | 분류기 | 최종 | confidence | uncertain | Guard | reason | 확률 |",
            "|---|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    if not errors:
        lines.append("| - | 오답 없음 | - | - | - | - | - | - | - | - |")
    for error in errors:
        lines.append(
            f"| {error['test_id']} | {error['text']} | {error['expected']} | "
            f"{error['classifier_intent']} | {error['final_intent']} | "
            f"{error['confidence']:.4f} | {error['uncertain']} | "
            f"{error['guard_triggered']} | {error['guard_reason'] or '-'} | "
            f"{_probabilities(error['probabilities'])} |"
        )
    lines.append("")


def create_report() -> None:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    training = artifact["training"]
    validation = training["metrics"]["validation"]
    v5 = evaluation["models"]["v5"]

    _write_loss_curve(
        OUTPUT_DIR / "intent_v5_loss_curve.svg",
        training["loss_curve"],
    )

    lines = [
        "# HEAPY Intent v5 MVP 모델 및 Safety Guard 평가 보고서",
        "",
        "- 작성자: 김진우",
        f"- 모델: `{artifact['model_version']}`",
        "- 상태: HEAPY MVP 기본 모델로 확정 및 `intent_linear.json`에 승격",
        "",
        "## 1. 데이터셋",
        "",
        "- 파일: `classifier/data/HEAPY_intent_dataset_v3_500.csv`",
        f"- 총 데이터: {training['example_count']}건",
        "- 라벨 분포: simple_lookup 120, comprehensive 130, general_chat 120, ignore 130",
        "- Blind 48과 정확히 겹치는 문장: 0건",
        "- 구성: v2 480건 + 복약 조회 comprehensive 10건 + 확정 진단 ignore 10건",
        "",
        "## 2. 모델 및 학습 설정",
        "",
        "- 구조: frozen Sentence Transformer → 768→4 Linear Layer → Softmax",
        "- Linear Layer: 기존 체크포인트 미사용, seed 42 랜덤 초기화",
        f"- Optimizer: {training['optimizer']}",
        f"- Learning rate: {training['learning_rate']}",
        f"- Weight decay: {training['weight_decay']}",
        f"- Loss: {training['loss_function']}",
        f"- Scheduler: {training['scheduler']}",
        f"- Batch: {training['batch_strategy']}",
        f"- 최대 epoch: {training['epochs']}",
        f"- Best epoch: {training['best_epoch']}",
        "- Early stopping patience: 40",
        "",
        "## 3. Validation",
        "",
        "| Accuracy | Macro F1 | Macro Precision | Macro Recall |",
        "|---:|---:|---:|---:|",
        f"| {validation['accuracy']:.4f} | {validation['macro_f1']:.4f} | "
        f"{validation['macro_precision']:.4f} | {validation['macro_recall']:.4f} |",
        "",
        "Confusion Matrix 순서는 `[simple_lookup, comprehensive, general_chat, ignore]`, 행은 정답, 열은 예측이다.",
        "",
        _format_matrix(validation["confusion_matrix"]),
        "",
        "![Intent v5 Loss Curve](intent_v5_loss_curve.svg)",
        "",
        "## 4. v5 Classifier 단독 외부 평가",
        "",
        "| Model | Dataset | Accuracy | Macro F1 |",
        "|---|---|---:|---:|",
    ]
    for model_name in ("v5",):
        for scope in ("기존 60", "독립 54", "Blind 48"):
            metrics = evaluation["models"][model_name]["classifier_only"][scope][
                "metrics"
            ]
            lines.append(
                f"| {model_name} | {scope} | {metrics['accuracy']:.4f} | "
                f"{metrics['macro_f1']:.4f} |"
            )

    lines.extend(
        [
            "",
            "## 5. v5 Classifier 단독 vs Safety Guard",
            "",
            "| Dataset | 방식 | Accuracy | Macro F1 | Macro Precision | Macro Recall |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for scope in ("기존 60", "독립 54", "Blind 48"):
        for label, key in (
            ("Linear classifier only", "classifier_only"),
            ("Linear classifier + Safety Guard", "with_safety_guard"),
        ):
            metrics = v5[key][scope]["metrics"]
            lines.append(
                f"| {scope} | {label} | {metrics['accuracy']:.4f} | "
                f"{metrics['macro_f1']:.4f} | "
                f"{metrics['macro_precision']:.4f} | "
                f"{metrics['macro_recall']:.4f} |"
            )

    lines.extend(
        [
            "",
            "## 6. 외부 평가 Confusion Matrix",
            "",
            "라벨 순서는 `[simple_lookup, comprehensive, general_chat, ignore]`이다.",
            "",
            "| Dataset | Classifier 단독 | Safety Guard 포함 | Guard 작동 수 |",
            "|---|---|---|---:|",
        ]
    )
    for scope in ("기존 60", "독립 54", "Blind 48"):
        classifier = v5["classifier_only"][scope]["metrics"]
        guarded = v5["with_safety_guard"][scope]
        lines.append(
            f"| {scope} | {_format_matrix(classifier['confusion_matrix'])} | "
            f"{_format_matrix(guarded['metrics']['confusion_matrix'])} | "
            f"{guarded['guard_trigger_count']} |"
        )

    lines.extend(
        [
            "",
            "## 7. Safety Guard 규칙",
            "",
            "- `definitive_diagnosis`: 질환 표현과 확정·진단·단정·보장 표현이 함께 있을 때 작동",
            "- `medication_decision`: 약 관련 표현과 용량·증감·중단·선택·변경 결정 표현이 함께 있을 때 작동",
            "- `medical_visit_decision`: 병원 방문 또는 응급 여부 결정을 요구할 때 작동",
            "- 단순 복약 목록·일정·기록 조회에는 작동하지 않음",
            "- 명시적 용량 변경이 없는 개인 복약 상호작용 조회에는 작동하지 않음",
            "- Guard 작동 시 규칙이 라우팅을 확정하므로 `confidence=1.0`, `uncertain=false` 사용",
            "",
            "필수 Guard 양성 8건과 음성 8건, 총 16개 문장 케이스가 단위 테스트를 통과했다.",
            "",
            "## 8. v5 오답 목록",
            "",
        ]
    )
    for scope in ("기존 60", "Blind 48"):
        _append_error_table(
            lines,
            f"{scope} Classifier 단독",
            v5["classifier_only"][scope]["errors"],
        )
        _append_error_table(
            lines,
            f"{scope} Safety Guard 포함",
            v5["with_safety_guard"][scope]["errors"],
        )

    lines.extend(
        [
            "## 9. 기존 Blind 핵심 3문장",
            "",
            "| ID | 정답 | Classifier | confidence | 확률 | Guard | reason | 최종 | 정답 여부 |",
            "|---|---|---|---:|---|---|---|---|---|",
        ]
    )
    for detail in evaluation["key_blind_details"]:
        lines.append(
            f"| {detail['test_id']} | {detail['expected']} | "
            f"{detail['classifier_intent']} | {detail['confidence']:.4f} | "
            f"{_probabilities(detail['classifier_probabilities'])} | "
            f"{detail['guard_triggered']} | {detail['guard_reason'] or '-'} | "
            f"{detail['final_intent']} | {detail['final_correct']} |"
        )

    lines.extend(
        [
            "",
            "## 10. 최종 판단",
            "",
            "v5 Classifier와 Guard 조합은 현재 MVP 기준 성능을 충족한다. Guard는 `혈압약 두알 먹어도됨?`을 ignore로 교정해 기존 60과 독립 54 성능을 추가로 높였으며 Blind 48에서는 성능을 유지했다.",
            "",
            "B-CP07은 comprehensive로 교정됐고 B-IG08은 Classifier와 Guard 모두 ignore로 처리했다. B-CP09의 confidence 0.6882 ignore 오분류는 알려진 잔여 오류로 기록하며, 팀 결정에 따라 v5와 Safety Guard를 현재 MVP 기본 모델로 사용한다.",
            "",
            "문장별 전체 결과는 `intent_v5_predictions.csv`, 상세 원본은 `intent_v5_evaluation.json`을 확인한다.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    try:
        create_report()
        print(f"보고서 저장: {REPORT_PATH}")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
