#!/usr/bin/env python3
"""원본 merged 데이터를 정책에 맞게 정제하고 Intent v6 split을 다시 만든다.

작성자: 김진우
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from classifier.script.intent_v6_utils import (
    LABELS,
    ROOT,
    audit_data_integrity,
    normalized_text,
    print_data_integrity,
    write_jsonl,
)


DEFAULT_SOURCE = ROOT / "classifier/data/HEAPY_intent_v6_merged_820.jsonl"
DEFAULT_TRAIN = ROOT / "classifier/data/HEAPY_intent_v6_train.jsonl"
DEFAULT_VALIDATION = ROOT / "classifier/data/HEAPY_intent_v6_validation.jsonl"
DEFAULT_TEST = ROOT / "classifier/data/HEAPY_intent_v6_test.jsonl"
DEFAULT_BLIND = ROOT / "classifier/data/HEAPY_intent_v6_blind48.jsonl"
DEFAULT_CLEANED = ROOT / "classifier/data/HEAPY_intent_v6_cleaned.jsonl"


PERSONAL_MEDICATION_ADDITIONS: tuple[str, ...] = (
    "오늘 저녁에 먹도록 등록된 내 약 목록을 확인해줘",
    "내 복약 목록 중 저녁 약만 조회해줘",
    "오늘 먹어야 하는 내 약들을 시간대별로 알려줘",
    "내가 지금 복용 중인 약 목록을 보여줘",
    "내 복약 정보에서 아침 약만 찾아줘",
    "이번 주 내 복약 일정을 정리해줘",
    "내 약 기록에서 어제 먹은 약을 확인해줘",
    "오늘 복용 예정인 약이 무엇인지 알려줘",
    "내 복약 내역을 최근 날짜순으로 보여줘",
    "저녁에 복용할 내 약이 어떤 건지 확인해줘",
    "내 복약 목록 전체를 한 번에 정리해줘",
    "오늘 약 뭐 먹어야 하는지 내 일정에서 찾아줘",
    "내가 등록한 약 중 오늘 먹는 약만 알려줘",
    "최근 내 복약 기록을 요약해줘",
    "내 복약 정보에 저장된 약 이름을 보여줘",
    "오늘 아침 약을 먹었는지 내 기록에서 확인해줘",
    "내 복약 기록에서 누락된 날짜를 찾아줘",
    "지금까지 저장한 내 약 복용 내역을 보여줘",
)

PERSONAL_SYMPTOM_ADDITIONS: tuple[str, ...] = (
    "아침부터 오른쪽 아랫배가 아프고 미열이 있어",
    "어젯밤부터 머리가 욱신거리고 빛을 보면 더 아파",
    "며칠째 목이 칼칼하고 기침이 계속 나",
    "조금만 걸어도 숨이 차고 심장이 빨리 뛰어",
    "오늘 계속 어지럽고 속이 메스꺼워",
    "손끝이 자꾸 저리고 감각이 둔한 느낌이야",
    "아침부터 몸에 힘이 없고 식은땀이 나",
    "최근에 갈증이 심하고 화장실을 자주 가",
    "며칠 전부터 귀가 아프고 분비물이 나와",
    "식사할 때마다 속이 불편하고 자꾸 토할 것 같아",
    "오늘 갑자기 가슴이 답답하고 두근거려",
    "요즘 허리가 계속 뻐근하고 오래 앉아 있으면 더 아파",
    "어제부터 열이 나고 오한이 반복돼",
    "최근 대변 색이 평소와 다르고 배가 더부룩해",
)

GENERAL_CHAT_ADDITIONS: tuple[str, ...] = (
    "오늘은 그냥 가볍게 대화하고 싶어",
    "네 설명을 들으니 이해가 잘 됐어",
    "창밖에 비가 내려서 분위기가 차분하네",
    "오늘 하루가 유난히 길게 느껴졌어",
    "너와 이야기하면 마음이 조금 편해",
    "내일은 여유 있는 하루였으면 좋겠다",
    "오늘 계획한 일을 전부 끝냈어",
    "잠깐 쉬면서 잡담이나 하자",
    "좋은 오후야, 오늘도 잘 부탁해",
    "방금 좋아하는 음악을 듣고 있었어",
    "오늘 기분이 꽤 평온해",
    "다음에 다시 이야기하자",
)

BLIND_COMPREHENSIVE: tuple[str, ...] = (
    "심장이 갑자기 빨리 뛰고 가슴이 벌렁거려. 내 증상 기록으로 남겨줘",
    "어제부터 오른쪽 아랫배가 아프고 열도 나",
    "조금만 걸어도 숨이 차고 가슴이 답답해",
    "며칠째 열이 오르내리고 오한도 있어",
    "최근 혈당이 높고 갈증이 자주 나",
    "한쪽 유두에서 분비물이 나와",
    "오늘 내 저녁 복약 목록 알려줘",
    "오늘 내 저녁 복약 목록 보여줘봐",
    "내가 현재 먹는 약들을 한 번에 보여줘",
    "내 복약 기록에서 이번 주에 빠뜨린 약이 있는지 알려줘",
    "오늘 아침에 먹기로 한 약 목록 확인해줘",
    "최근 내 복약 내역을 날짜별로 정리해줘",
)

BLIND_GENERAL_CHAT: tuple[str, ...] = (
    "오늘은 건강 얘기 말고 그냥 잡담하고 싶어",
    "설명 고마워, 이제 이해됐어",
    "지금 창밖에 비가 오네",
    "오늘 하루가 꽤 길었어",
    "너랑 이야기하니까 마음이 편하다",
    "내일은 조금 여유로웠으면 좋겠어",
    "오늘 계획한 일을 다 끝냈어",
    "잠깐 쉬면서 이야기하자",
    "좋은 오후야",
    "방금 음악을 듣고 있었어",
    "오늘은 기분이 꽤 괜찮아",
    "다음에 또 이야기하자",
)


def _read_source(path: Path) -> list[dict[str, Any]]:
    """메타데이터를 보존한 채 원본 JSONL을 읽는다."""
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                item: Any = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"잘못된 JSON입니다: {path}:{line_number} ({error.msg})"
                ) from error
            if not isinstance(item, dict):
                raise ValueError(f"JSON 객체가 아닙니다: {path}:{line_number}")
            text = str(item.get("text", "")).strip()
            label = str(item.get("label", "")).strip()
            if not text or label not in LABELS:
                raise ValueError(f"잘못된 text 또는 label입니다: {path}:{line_number}")
            rows.append(dict(item))
    return rows


def policy_label(row: dict[str, Any]) -> str:
    """확정된 복약·증상 정책을 적용하되 ignore 우선순위는 보존한다."""
    label = str(row["label"])
    if label == "ignore":
        return label

    text = str(row["text"]).strip()
    topic = str(row.get("topic", "")).strip()
    source = str(row.get("source", "")).strip()

    # 개인 증상·신체 상태 서술은 향후 기록 경로를 위해 comprehensive로 보낸다.
    if label == "general_chat" and topic in {"증상공유", "상태공유"}:
        return "comprehensive"
    if label == "general_chat" and source == "symptom_collection_v6":
        personal_symptom = (
            (text.startswith("요즘 ") and " 때문에 걱정돼" in text)
            or (text.startswith("오늘은 ") and " 있는 것 같아" in text)
        )
        if personal_symptom:
            return "comprehensive"

    # 개인 복약 목록·일정·기록 조회는 치료 결정이 아니라 개인 데이터 조회다.
    medication_terms = ("약", "복약", "복용")
    personal_terms = ("내 ", "내가", "오늘", "이번 주", "최근")
    lookup_terms = ("목록", "기록", "내역", "일정", "정보", "알려", "보여", "확인", "조회", "정리")
    if (
        any(term in text for term in medication_terms)
        and any(term in text for term in personal_terms)
        and any(term in text for term in lookup_terms)
    ):
        return "comprehensive"
    return label


def _deduplicate_and_relabel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """공백 정규화 문장을 하나만 남기고 정책 라벨과 변경 근거를 기록한다."""
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        text = str(row["text"]).strip()
        key = normalized_text(text)
        new_label = policy_label(row)
        candidate = {
            "text": text,
            "label": new_label,
            "source": str(row.get("source", "source_merged_v6")),
            "topic": str(row.get("topic", "")),
            "original_label": str(row["label"]),
            "policy_changed": new_label != str(row["label"]),
        }
        previous = unique.get(key)
        if previous is not None and previous["label"] != candidate["label"]:
            raise ValueError(
                "중복 문장에 서로 다른 정책 라벨이 있습니다: "
                f"{text} ({previous['label']} / {candidate['label']})"
            )
        unique.setdefault(key, candidate)
    return list(unique.values())


def _add_policy_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """취약 경계의 다양한 표현을 중복 없이 보강한다."""
    result = list(rows)
    existing = {normalized_text(str(row["text"])) for row in result}
    additions = (
        [(text, "comprehensive", "policy_medication_v6") for text in PERSONAL_MEDICATION_ADDITIONS]
        + [(text, "comprehensive", "policy_symptom_v6") for text in PERSONAL_SYMPTOM_ADDITIONS]
        + [(text, "general_chat", "policy_general_chat_v6") for text in GENERAL_CHAT_ADDITIONS]
    )
    for text, label, source in additions:
        key = normalized_text(text)
        if key in existing:
            continue
        result.append(
            {
                "text": text,
                "label": label,
                "source": source,
                "topic": "policy_boundary",
                "original_label": label,
                "policy_changed": False,
            }
        )
        existing.add(key)
    return result


def _build_blind(source_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """기존 Simple·Ignore를 보존하고 취약 경계와 고유 Chat으로 Blind를 재구성한다."""
    by_label: dict[str, list[str]] = {label: [] for label in LABELS}
    seen: set[str] = set()
    for row in source_rows:
        label = str(row["label"])
        text = str(row["text"]).strip()
        key = normalized_text(text)
        if label not in {"simple_lookup", "ignore"} or key in seen:
            continue
        by_label[label].append(text)
        seen.add(key)

    if len(by_label["simple_lookup"]) < 12 or len(by_label["ignore"]) < 12:
        raise ValueError("Blind의 simple_lookup 또는 ignore 고유 문장이 12건 미만입니다.")
    rows = [
        {"text": text, "label": "simple_lookup"}
        for text in by_label["simple_lookup"][:12]
    ]
    rows.extend(
        {"text": text, "label": "comprehensive"}
        for text in BLIND_COMPREHENSIVE
    )
    rows.extend(
        {"text": text, "label": "general_chat"}
        for text in BLIND_GENERAL_CHAT
    )
    rows.extend(
        {"text": text, "label": "ignore"}
        for text in by_label["ignore"][:12]
    )
    if len({normalized_text(row["text"]) for row in rows}) != 48:
        raise ValueError("재구성한 Blind 48에 중복 문장이 있습니다.")
    return rows


def _stratified_split(
    rows: list[dict[str, Any]],
    seed: int,
) -> dict[str, list[dict[str, str]]]:
    """라벨별 80:10:10 비율로 고정 seed 재분할한다."""
    random_generator = random.Random(seed)
    result = {"train": [], "validation": [], "test": []}
    for label in LABELS:
        label_rows = [row for row in rows if row["label"] == label]
        random_generator.shuffle(label_rows)
        validation_count = max(1, round(len(label_rows) * 0.1))
        test_count = max(1, round(len(label_rows) * 0.1))
        validation_rows = label_rows[:validation_count]
        test_rows = label_rows[validation_count:validation_count + test_count]
        train_rows = label_rows[validation_count + test_count:]
        for split_name, selected in (
            ("train", train_rows),
            ("validation", validation_rows),
            ("test", test_rows),
        ):
            result[split_name].extend(
                {"text": str(row["text"]), "label": str(row["label"])}
                for row in selected
            )
    for selected in result.values():
        random_generator.shuffle(selected)
    return result


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    """정제·재라벨링·Blind 재구성·재분할을 수행하고 파일을 갱신한다."""
    source_rows = _read_source(args.source.resolve())
    blind_source_rows = _read_source(args.blind.resolve())
    blind_rows = _build_blind(blind_source_rows)
    blind_texts = {normalized_text(row["text"]) for row in blind_rows}

    cleaned = _add_policy_examples(_deduplicate_and_relabel(source_rows))
    before_exclusion = len(cleaned)
    cleaned = [
        row
        for row in cleaned
        if normalized_text(str(row["text"])) not in blind_texts
    ]
    blind_overlap_removed = before_exclusion - len(cleaned)
    splits = _stratified_split(cleaned, args.seed)
    datasets = {**splits, "blind": blind_rows}
    paths = {
        "train": args.train.resolve(),
        "validation": args.validation.resolve(),
        "test": args.test.resolve(),
        "blind": args.blind.resolve(),
    }
    integrity = audit_data_integrity(datasets, paths)
    if integrity["warnings"]:
        raise ValueError(
            "정제 후에도 데이터 중복 또는 split 누수가 남았습니다: "
            + " / ".join(integrity["warnings"])
        )

    write_jsonl(args.cleaned.resolve(), cleaned)
    write_jsonl(paths["train"], splits["train"])
    write_jsonl(paths["validation"], splits["validation"])
    write_jsonl(paths["test"], splits["test"])
    write_jsonl(paths["blind"], blind_rows)

    changed = Counter(
        row["original_label"]
        for row in cleaned
        if bool(row.get("policy_changed"))
    )
    print(f"원본 행: {len(source_rows)}")
    print(f"정규화 중복 제거 후 정책 데이터: {len(cleaned)}")
    print(f"Blind 중복 방지를 위해 제외한 문장: {blind_overlap_removed}")
    print(f"정책 재라벨링: {sum(changed.values())}건")
    print_data_integrity(integrity)
    return {
        "source_count": len(source_rows),
        "cleaned_count": len(cleaned),
        "blind_overlap_removed": blind_overlap_removed,
        "policy_relabel_count": sum(changed.values()),
        "integrity": integrity,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--test", type=Path, default=DEFAULT_TEST)
    parser.add_argument("--blind", type=Path, default=DEFAULT_BLIND)
    parser.add_argument("--cleaned", type=Path, default=DEFAULT_CLEANED)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        prepare(build_parser().parse_args())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
