"""골든 데이터셋 로딩과 층화 표본 추출."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATASET = (
    Path("data")
    / "test_golden_dataset"
    / "RAG_골든데이터셋_최종_질병_복약_건강검진_2290.jsonl"
)


@dataclass(frozen=True)
class GoldenItem:
    """평가 1건에 필요한 골든 레코드."""

    question_id: str
    question: str
    split: str
    domain: str
    question_type: str
    difficulty: str
    answerable: bool
    expected_behavior: str
    reference_answer: str
    gold_document_ids: list[str]
    acceptable_document_ids: list[str]
    gold_contexts: list[str]
    source_label: str
    source_uri: str
    target: str
    evaluation: dict
    raw: dict

    @property
    def relevant_document_ids(self) -> set[str]:
        """정답으로 인정하는 문서 ID 집합(허용 ID 우선)."""
        return set(self.acceptable_document_ids or self.gold_document_ids)

    @property
    def strict_document_ids(self) -> set[str]:
        """재현율 분모로 쓰는 정답 문서 ID 집합."""
        return set(self.gold_document_ids)


def load_dataset(path: Path = DEFAULT_DATASET) -> list[GoldenItem]:
    """JSONL 골든 데이터셋을 GoldenItem 목록으로 읽는다."""
    items: list[GoldenItem] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            items.append(
                GoldenItem(
                    question_id=row["question_id"],
                    question=row["question"],
                    split=row.get("split", ""),
                    domain=row.get("domain", ""),
                    question_type=row.get("question_type", ""),
                    difficulty=row.get("difficulty", ""),
                    answerable=bool(row.get("answerable", True)),
                    expected_behavior=row.get("expected_behavior", ""),
                    reference_answer=row.get("reference_answer", ""),
                    gold_document_ids=list(row.get("gold_document_ids") or []),
                    acceptable_document_ids=list(
                        row.get("acceptable_document_ids") or []
                    ),
                    gold_contexts=list(row.get("gold_contexts") or []),
                    source_label=row.get("source_label", ""),
                    source_uri=row.get("source_uri", ""),
                    target=row.get("target", ""),
                    evaluation=dict(row.get("evaluation") or {}),
                    raw=row,
                )
            )
    return items


def stratify_key(item: GoldenItem) -> tuple[str, str, str, bool]:
    """층화 표본의 층을 정의한다."""
    return (item.domain, item.split, item.difficulty, item.answerable)


def stratified_sample(
    items: list[GoldenItem],
    sample_size: int,
    seed: int = 20260806,
) -> list[GoldenItem]:
    """도메인·split·난이도·답변가능 여부 비율을 유지하며 표본을 뽑는다."""
    if sample_size <= 0 or sample_size >= len(items):
        return list(items)

    strata: dict[tuple, list[GoldenItem]] = defaultdict(list)
    for item in items:
        strata[stratify_key(item)].append(item)

    rng = random.Random(seed)
    total = len(items)
    selected: list[GoldenItem] = []
    remainders: list[tuple[float, tuple, list[GoldenItem]]] = []

    for key, members in sorted(strata.items(), key=lambda pair: str(pair[0])):
        rng.shuffle(members)
        exact = sample_size * len(members) / total
        take = int(exact)
        selected.extend(members[:take])
        remainders.append((exact - take, key, members[take:]))

    # 내림 처리로 남은 자리를 소수부가 큰 층부터 채운다.
    remainders.sort(key=lambda entry: (-entry[0], str(entry[1])))
    index = 0
    while len(selected) < sample_size and remainders:
        _, _, leftovers = remainders[index % len(remainders)]
        if leftovers:
            selected.append(leftovers.pop(0))
        elif all(not entry[2] for entry in remainders):
            break
        index += 1

    selected.sort(key=lambda item: item.question_id)
    return selected[:sample_size]
