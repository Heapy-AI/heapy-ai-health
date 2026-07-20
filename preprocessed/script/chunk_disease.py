#!/usr/bin/env python3
"""② 전처리(preprocessed/disease_info) → ③ 청크(vdb/chunk/disease_info).

- AIHub: 정제된 QA를 question+answer 병합해 1 QA = 1 청크 (분할 없음).
- KDCA : 섹션을 '크기 적응형'으로 청킹 — 작은 건 합치고(≤MERGE_MAX) 큰 건 문장단위로 분할(≈BUDGET),
         초단문 파편(<MIN)은 이전 청크에 흡수.
출력 스키마: {"id","text","metadata"} (ingest_vdb.py 로더가 top-level id 사용)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from transformers import AutoTokenizer

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]   # preprocessed/script/ → repo 루트
PRE = ROOT / "preprocessed" / "disease_info"
OUT = ROOT / "vdb" / "chunk" / "disease_info"

BUDGET = 105      # 큰 섹션 분할 목표 토큰
MERGE_MAX = 125   # 작은 섹션 병합 상한
MIN = 30          # 이보다 작은 청크는 이전 청크에 흡수

_tok = AutoTokenizer.from_pretrained("jhgan/ko-sroberta-multitask")
def ntok(t: str) -> int:
    return len(_tok.encode(t, add_special_tokens=False))


# ---------------- AIHub: 병합만 ----------------
def chunk_aihub() -> tuple[int, Counter]:
    src = PRE / "aihub"
    stat = Counter()
    total = 0
    for jf in sorted(src.glob("*.jsonl")):
        out_lines = []
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rec = {
                "id": f"aihub-{r['qa_id']}",
                "text": f"{r['question']}\n\n{r['answer']}",
                "metadata": {
                    "qa_id": r["qa_id"],
                    "specialty": r["specialty"],
                    "q_type": r["q_type"],
                    "source": r["source"],
                    "source_label": r["source_label"],
                    "review_status": r["review_status"],
                },
            }
            out_lines.append(json.dumps(rec, ensure_ascii=False))
        (OUT / f"aihub_{jf.stem}.jsonl").write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        stat[jf.stem] = len(out_lines)
        total += len(out_lines)
    return total, stat


# ---------------- KDCA: 크기 적응형 ----------------
def split_sents(text: str) -> list[str]:
    parts = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts += [s.strip() for s in re.split(r"(?<=[.!?。])\s+", line) if s.strip()]
    return parts


def hard_split(s: str, budget: int) -> list[str]:
    words, out, cur = s.split(" "), [], []
    for w in words:
        cur.append(w)
        if ntok(" ".join(cur)) >= budget:
            out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def chunk_sections(sections: list[dict]) -> list[tuple[str, str]]:
    chunks, buf_secs, buf, buf_tok = [], [], [], 0

    def flush():
        nonlocal buf_secs, buf, buf_tok
        if buf:
            label = " / ".join(dict.fromkeys(buf_secs))
            chunks.append((label, "\n".join(buf).strip()))
            buf_secs, buf, buf_tok = [], [], 0

    for sec in sections:
        nm, content = sec["name"], sec["content"]
        for s in split_sents(content):
            stk = ntok(s)
            if stk > BUDGET:
                flush()
                for piece in hard_split(s, BUDGET):
                    chunks.append((nm, piece))
                continue
            if buf_tok + stk > MERGE_MAX:
                flush()
            buf_secs.append(nm); buf.append(s); buf_tok += stk
    flush()

    # 초단문 파편 흡수: <MIN 토큰이면 이전 청크에 병합
    merged: list[tuple[str, str]] = []
    for label, body in chunks:
        if merged and ntok(body) < MIN:
            plabel, pbody = merged[-1]
            new_label = plabel if label in plabel.split(" / ") else f"{plabel} / {label}"
            merged[-1] = (new_label, pbody + "\n" + body)
        else:
            merged.append((label, body))
    return merged


def chunk_kdca() -> tuple[int, Counter]:
    src = PRE / "kdca"
    per_super: dict[str, list[str]] = {}
    stat = Counter()
    total = 0
    for jf in sorted(src.glob("*.json")):
        doc = json.loads(jf.read_text(encoding="utf-8"))
        disease, sn = doc["disease"], doc["cntnts_sn"]
        sc = doc.get("superclass") or "기타"
        for i, (label, body) in enumerate(chunk_sections(doc["sections"])):
            rec = {
                "id": f"kdca-{sn}-{i}",
                "text": f"{disease} - {label}\n\n{body}",
                "metadata": {
                    "disease": disease,
                    "section": label,
                    "superclass": sc,
                    "cntnts_sn": sn,
                    "source": doc["source"],
                    "source_label": doc["source_label"],
                    "review_status": doc["review_status"],
                },
            }
            per_super.setdefault(sc, []).append(json.dumps(rec, ensure_ascii=False))
            total += 1
        stat[disease] += 0  # touch
    for sc, lines in per_super.items():
        safe = re.sub(r"[\\/:*?\"<>|\s]+", "_", sc)
        (OUT / f"kdca_{safe}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        stat[f"[{sc}]"] = len(lines)
    return total, stat


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    a_total = k_total = 0
    if (PRE / "aihub").exists():
        a_total, a_stat = chunk_aihub()
        print(f"AIHub 청크: {a_total:,} (진료과 {len([k for k in a_stat])}개)")
    if (PRE / "kdca").exists():
        k_total, k_stat = chunk_kdca()
        print(f"KDCA 청크: {k_total:,}")
        for k, n in k_stat.items():
            if k.startswith("["):
                print(f"  {k}: {n:,}")
    print(f"\n총 disease_info 청크: {a_total + k_total:,} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
