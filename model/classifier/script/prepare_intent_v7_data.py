#!/usr/bin/env python3
"""Intent v7 정책으로 데이터 재라벨링·보강·분할을 수행한다.

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

from model.classifier.script.intent_v6_utils import (
    LABELS,
    ROOT,
    audit_data_integrity,
    normalized_text,
    print_data_integrity,
    write_jsonl,
)
from model.classifier.script.prepare_intent_v6_data import policy_label as v6_policy_label


DEFAULT_SOURCE = ROOT / "classifier/data/HEAPY_intent_v6_merged_820.jsonl"
DEFAULT_TRAIN = ROOT / "classifier/data/HEAPY_intent_v7_train.jsonl"
DEFAULT_VALIDATION = ROOT / "classifier/data/HEAPY_intent_v7_validation.jsonl"
DEFAULT_TEST = ROOT / "classifier/data/HEAPY_intent_v7_test.jsonl"
DEFAULT_BLIND = ROOT / "classifier/data/HEAPY_intent_v7_blind48.jsonl"
DEFAULT_CLEANED = ROOT / "classifier/data/HEAPY_intent_v7_cleaned.jsonl"


OUT_OF_SCOPE_ADDITIONS: tuple[str, ...] = (
    "오늘 코스피 전망 알려줘",
    "삼성전자 주가 지금 얼마야?",
    "비트코인 매수 타이밍을 추천해줘",
    "이번 달 환율이 오를까?",
    "적금 금리가 높은 은행을 골라줘",
    "내 주식 포트폴리오를 분석해줘",
    "서울 내일 날씨가 어때?",
    "이번 주말 부산에 비 와?",
    "오늘 미세먼지 수치 알려줘",
    "태풍이 언제 상륙하는지 알려줘",
    "제주도 여행하기 좋은 계절이 언제야?",
    "강릉 2박 3일 여행 코스 짜줘",
    "서울역 근처 맛집 추천해줘",
    "데이트하기 좋은 카페를 골라줘",
    "다음 주 비행기 표를 찾아줘",
    "호텔 예약할 때 싸게 잡는 법 알려줘",
    "오늘 프로야구 경기 결과 알려줘",
    "축구 국가대표 일정이 언제야?",
    "농구 플레이오프 순위를 알려줘",
    "손흥민 이번 시즌 골 수가 몇 개야?",
    "롤에서 초보자가 하기 좋은 챔피언 추천해줘",
    "이번 패치에서 강한 캐릭터가 뭐야?",
    "플레이스테이션 게임 추천해줘",
    "스팀 세일 중 살 만한 게임 알려줘",
    "파이썬으로 웹 크롤러 만들어줘",
    "자바스크립트 배열 정렬 코드를 알려줘",
    "리액트 상태 관리 방법을 설명해줘",
    "깃 충돌 해결하는 명령어가 뭐야?",
    "SQL 조인 예제를 만들어줘",
    "도커 이미지 빌드가 실패하는 이유를 찾아줘",
    "노트북 가성비 좋은 제품 추천해줘",
    "휴대폰을 새로 사려는데 뭘 사면 좋아?",
    "무선 이어폰 두 제품을 비교해줘",
    "여름용 운동화를 추천해줘",
    "이 옷에 어울리는 가방을 골라줘",
    "중고차를 살 때 확인할 점 알려줘",
    "주말에 볼 만한 영화 추천해줘",
    "요즘 인기 있는 드라마가 뭐야?",
    "출근할 때 들을 노래 추천해줘",
    "이 소설의 줄거리를 요약해줘",
    "사진을 빈티지 느낌으로 보정하고 싶어",
    "유튜브 영상 제목을 지어줘",
    "영어 이메일을 자연스럽게 번역해줘",
    "일본어 인사말을 알려줘",
    "자기소개서를 다듬어줘",
    "회의록을 세 줄로 요약해줘",
    "발표 대본을 자연스럽게 고쳐줘",
    "수학 방정식 문제를 풀어줘",
    "한국사 시험 문제를 만들어줘",
    "영어 단어 암기 계획을 짜줘",
    "물리학 뉴턴 법칙을 설명해줘",
    "논문 참고문헌 형식을 바꿔줘",
    "취업 면접 질문을 추천해줘",
    "오늘 할 일을 우선순위로 정리해줘",
    "프로젝트 일정을 간트차트로 만들어줘",
    "친구 생일 선물을 추천해줘",
    "집들이 음식 메뉴를 골라줘",
    "반려견 산책 훈련 방법 알려줘",
    "고양이가 좋아하는 장난감이 뭐야?",
    "화분에 물을 얼마나 자주 줘야 해?",
    "자동차 엔진오일 교체 주기를 알려줘",
    "전세 계약할 때 주의할 점 알려줘",
    "이사 업체 고르는 방법을 알려줘",
    "방 인테리어 색 조합을 추천해줘",
    "세탁기 냄새 없애는 법 알려줘",
    "김치볶음밥 레시피 알려줘",
    "쿠키를 바삭하게 굽는 방법이 뭐야?",
    "저녁 배달 메뉴 하나 골라줘",
    "커피 원두 보관법을 알려줘",
    "와인과 어울리는 안주 추천해줘",
    "사진 속 글자를 번역해줘",
    "가족 여행 사진으로 앨범 구성해줘",
    "결혼식 축사를 작성해줘",
    "닉네임을 열 개 추천해줘",
    "오늘의 운세를 알려줘",
    "사주를 봐줘",
    "로또 번호를 추천해줘",
    "꿈 해몽을 해줘",
    "서울 지하철 막차 시간이 언제야?",
    "집에서 회사까지 빠른 길 찾아줘",
    "택배가 언제 도착하는지 확인해줘",
    "공연 티켓 예매 일정을 알려줘",
)

BLIND_ROWS: tuple[tuple[str, str], ...] = (
    ("고혈압이 어떤 질환인지 알려줘", "simple_lookup"),
    ("당뇨병에서 흔한 증상을 설명해줘", "simple_lookup"),
    ("판콜에스내복액의 효능과 주의사항이 뭐야?", "simple_lookup"),
    ("공복혈당 검사는 무엇을 확인해?", "simple_lookup"),
    ("AST와 ALT의 차이를 알려줘", "simple_lookup"),
    ("감기의 일반적인 예방법을 알려줘", "simple_lookup"),
    ("빈혈의 대표적인 원인이 뭐야?", "simple_lookup"),
    ("정상B 판정은 무슨 뜻이야?", "simple_lookup"),
    ("타이레놀을 복용할 때 주의할 점 알려줘", "simple_lookup"),
    ("고지혈증의 위험요인을 알려줘", "simple_lookup"),
    ("혈색소 수치는 무엇을 의미해?", "simple_lookup"),
    ("위염의 증상과 생활 관리법을 알려줘", "simple_lookup"),
    ("감기 걸린 것 같은데 집에서 어떻게 관리할까?", "comprehensive"),
    ("숨이 차고 가슴이 아픈데 지금 뭘 해야 해?", "comprehensive"),
    ("내 검사 결과만 보고 당뇨병인지 확정해줘", "comprehensive"),
    ("이 약을 두 배로 먹어도 되는지 결정해줘", "comprehensive"),
    ("복용 중인 약을 오늘부터 끊어도 될까?", "comprehensive"),
    ("내 혈압 기록과 증상을 같이 봐줘", "comprehensive"),
    ("열과 기침이 사흘째 계속되는데 어떤 점을 확인해야 해?", "comprehensive"),
    ("두 약을 같이 복용할 때 내 상황에서 주의할 점이 뭐야?", "comprehensive"),
    ("내 검진 수치와 복약 기록을 함께 설명해줘", "comprehensive"),
    ("병원에 안 가도 되는지 대신 판단해줘", "comprehensive"),
    ("갑자기 어지럽고 식은땀이 나는데 어떻게 해야 해?", "comprehensive"),
    ("내 증상에 맞는 약과 용량을 정해줘", "comprehensive"),
    ("안녕, 오늘도 잘 부탁해", "general_chat"),
    ("설명해줘서 고마워", "general_chat"),
    ("오늘 기분이 꽤 좋아", "general_chat"),
    ("잠깐 가볍게 이야기하자", "general_chat"),
    ("너는 어떤 도움을 줄 수 있어?", "general_chat"),
    ("좋은 아침이야", "general_chat"),
    ("오늘 하루가 길게 느껴졌어", "general_chat"),
    ("다음에 다시 물어볼게", "general_chat"),
    ("답변이 이해하기 쉬웠어", "general_chat"),
    ("요즘 조금 지치는 기분이야", "general_chat"),
    ("반가워", "general_chat"),
    ("잘 자라고 인사해줘", "general_chat"),
    ("내일 서울 날씨 알려줘", "ignore"),
    ("이번 주에 살 만한 주식 추천해줘", "ignore"),
    ("파이썬 계산기 코드를 작성해줘", "ignore"),
    ("주말 영화 한 편 골라줘", "ignore"),
    ("부산 여행 일정을 만들어줘", "ignore"),
    ("축구 경기 결과 알려줘", "ignore"),
    ("가성비 노트북 추천해줘", "ignore"),
    ("영어 문장을 번역해줘", "ignore"),
    ("저녁 메뉴를 골라줘", "ignore"),
    ("자기소개서를 첨삭해줘", "ignore"),
    ("비트코인 가격 전망이 어때?", "ignore"),
    ("게임 캐릭터 공략을 알려줘", "ignore"),
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not str(value.get("text", "")).strip():
                raise ValueError(f"잘못된 JSONL 행입니다: {path}:{line_number}")
            rows.append(dict(value))
    return rows


def policy_label(row: dict[str, Any]) -> str:
    """ignore를 서비스 외 질문으로 축소하고 의료 질문은 처리 경로로 복귀시킨다."""
    label = str(row["label"])
    topic = str(row.get("topic", "")).strip()
    if label == "ignore":
        return "ignore" if topic == "서비스외" else "comprehensive"
    return v6_policy_label(row)


def _clean_and_relabel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        text = str(row["text"]).strip()
        key = normalized_text(text)
        label = policy_label(row)
        candidate = {
            "text": text,
            "label": label,
            "source": str(row.get("source", "intent_v6_merged")),
            "topic": str(row.get("topic", "")),
            "original_label": str(row["label"]),
            "policy_changed": label != str(row["label"]),
        }
        previous = unique.get(key)
        if previous is not None and previous["label"] != label:
            raise ValueError(f"중복 문장의 라벨이 충돌합니다: {text}")
        unique.setdefault(key, candidate)

    for text in OUT_OF_SCOPE_ADDITIONS:
        key = normalized_text(text)
        unique.setdefault(
            key,
            {
                "text": text,
                "label": "ignore",
                "source": "out_of_scope_policy_v7",
                "topic": "서비스외",
                "original_label": "ignore",
                "policy_changed": False,
            },
        )
    return list(unique.values())


def _stratified_split(
    rows: list[dict[str, Any]],
    seed: int,
) -> dict[str, list[dict[str, str]]]:
    random_generator = random.Random(seed)
    result = {"train": [], "validation": [], "test": []}
    for label in LABELS:
        label_rows = [row for row in rows if row["label"] == label]
        random_generator.shuffle(label_rows)
        validation_count = max(1, round(len(label_rows) * 0.1))
        test_count = max(1, round(len(label_rows) * 0.1))
        for split_name, selected in (
            ("validation", label_rows[:validation_count]),
            ("test", label_rows[validation_count:validation_count + test_count]),
            ("train", label_rows[validation_count + test_count:]),
        ):
            result[split_name].extend(
                {"text": str(row["text"]), "label": str(row["label"])}
                for row in selected
            )
    for selected in result.values():
        random_generator.shuffle(selected)
    return result


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    source_rows = _read_jsonl(args.source.resolve())
    blind_rows = [{"text": text, "label": label} for text, label in BLIND_ROWS]
    blind_texts = {normalized_text(row["text"]) for row in blind_rows}
    cleaned = [
        row
        for row in _clean_and_relabel(source_rows)
        if normalized_text(str(row["text"])) not in blind_texts
    ]
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
        raise ValueError(" / ".join(integrity["warnings"]))

    write_jsonl(args.cleaned.resolve(), cleaned)
    for name in ("train", "validation", "test"):
        write_jsonl(paths[name], splits[name])
    write_jsonl(paths["blind"], blind_rows)

    transitions = Counter(
        f"{row['original_label']}->{row['label']}"
        for row in cleaned
        if row["policy_changed"]
    )
    print(f"원본 행: {len(source_rows)}")
    print(f"v7 정책 데이터: {len(cleaned)}")
    print(f"재라벨링: {dict(transitions)}")
    print_data_integrity(integrity)
    return {
        "source_count": len(source_rows),
        "cleaned_count": len(cleaned),
        "transitions": dict(transitions),
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
