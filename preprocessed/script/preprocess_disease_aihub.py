#!/usr/bin/env python3
"""① 원천 AIHub QA(data/disease_info) → ② 전처리(preprocessed/disease_info/aihub).

전처리 = 정제만(청킹 아님). q_type 분기로 보기/번호 제거 후 question/answer를 '분리 보존'.
청킹(병합)은 별도 단계(chunk_disease.py)에서 수행한다.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]   # preprocessed/script/ → repo 루트
DATA = ROOT / "data"
DISEASE = next(p for p in DATA.iterdir() if p.is_dir() and "disease" in p.name.lower())
OUT_DIR = ROOT / "preprocessed" / "disease_info" / "aihub"

DATASET_SRC = {
    "전문": ("AIHub 전문 의학지식 데이터",
             "https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71874"),
    "필수의료": ("AIHub 필수의료 의학지식 데이터",
                 "https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71875"),
}
QTYPE_LABEL = {1: "객관식", 2: "단답", 3: "서술"}
REVIEW_STATUS = "UNVERIFIED_AIHUB"

_CHOICE_BLOCK = re.compile(r"(?ms)^\s*1\)\s.*$")
_HAS_SECOND = re.compile(r"(?m)^\s*2\)")
_ANS_NUM = re.compile(r"^\s*(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+\))\s*")


def dataset_key(f: Path) -> str:
    return "필수의료" if "필수의료" in f.relative_to(DISEASE).parts[0] else "전문"


def specialty_of(f: Path) -> str:
    for p in f.relative_to(DISEASE).parts:
        if p.startswith("TL_"):
            return p[3:]
    return "미분류"


def clean_question(q: str, q_type: int) -> tuple[str, bool]:
    if q_type != 1:
        return q.strip(), False
    m = _CHOICE_BLOCK.search(q)
    if m and _HAS_SECOND.search(m.group(0)):
        return q[: m.start()].strip(), False
    return q.strip(), True


def clean_answer(a: str, q_type: int) -> str:
    a = a.strip()
    return _ANS_NUM.sub("", a).strip() if q_type == 1 else a


def main() -> int:
    files = list(DISEASE.rglob("*.json"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    buckets = defaultdict(list)
    stat = Counter()
    flagged = empty = 0

    for f in files:
        try:
            o = json.loads(f.read_bytes().decode("utf-8-sig"))
        except Exception:
            flagged += 1
            continue
        qt = o.get("q_type")
        spec = specialty_of(f)
        label, url = DATASET_SRC[dataset_key(f)]
        q, miss = clean_question(str(o.get("question", "")), qt)
        a = clean_answer(str(o.get("answer", "")), qt)
        if miss:
            flagged += 1
        if not q or not a:
            empty += 1
            continue
        rec = {
            "qa_id": o.get("qa_id"),
            "specialty": spec,
            "q_type": QTYPE_LABEL.get(qt, str(qt)),
            "question": q,
            "answer": a,
            "source": url,
            "source_label": label,
            "review_status": REVIEW_STATUS,
        }
        buckets[spec].append(json.dumps(rec, ensure_ascii=False))
        stat[spec] += 1

    for spec, lines in sorted(buckets.items()):
        (OUT_DIR / f"{spec}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"원천 {len(files):,} → 전처리 레코드 {sum(stat.values()):,} (진료과 {len(buckets)}개) -> {OUT_DIR}")
    print(f"보기제거 실패 플래그: {flagged}, 빈 값 제외: {empty}")
    for spec, n in stat.most_common():
        print(f"  {n:>6,}  {spec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
