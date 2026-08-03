# -*- coding: utf-8 -*-
"""disease VDB 빌더 (Pinecone 스키마).

입력: output/*.json  (category=='disease')
  - 이미지 OCR 텍스트는 pipeline.py 단계에서 이미 섹션 content에 병합됨(canonical).
    (pipeline.py --extractions ... 로 병합 → output 이 이미 완전본)
처리:
  1) 기존 chunk_disease.py 청킹 재사용 → text = "{질환} - {섹션}\n\n{본문}"
  2) Pinecone 스키마 metadata:
     primary_key, doc_type, categories(list[str]), kcd_code(스칼라), kcd_primary_name,
     kcd_codes(list[str]), related_diseases(list[str]), section, cntnts_sn,
     source, source_label, review_status, created_at, has_image_text
     * list/None 은 Pinecone 규칙상 비면 키 자체를 생략(빈배열/null 금지)
출력: vdb/chunk/disease_info/kdca_disease_enriched.jsonl

사용: python integrate_and_build_vdb.py [--out <jsonl>]
"""
from __future__ import annotations
import argparse, json, os, glob, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # preprocessed/script
sys.stdout.reconfigure(encoding="utf-8")
from chunk_disease import chunk_sections, tbl_prefix   # 기존 청킹 재사용(ko-sroberta 토크나이저)
from utils import extract_related_diseases

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUTPUT = os.path.join(ROOT, "output")
DEFAULT_OUT = os.path.join(ROOT, "vdb", "chunk", "disease_info", "kdca_disease_enriched.jsonl")
TODAY = datetime.date.today().isoformat()

# ---- KCD 대분류(챕터) 매핑 ----
_KD = json.load(open(os.path.join(HERE, "kcd_dict.json"), encoding="utf-8"))
def _scalar(code):
    m = re.match(r"([A-Z])(\d{1,2})", str(code).strip())
    return (ord(m.group(1)) - ord('A')) * 100 + int(m.group(2)) if m else None
_CH = []
for ch in _KD["chapters"]:
    a, _, b = ch["range"].partition("-")
    sa, sb = _scalar(a), _scalar(b or a)
    if sa is not None and sb is not None:
        _CH.append((sa, sb, ch["name"]))

def code_to_chapter(code):
    s = _scalar(code)
    if s is None: return None
    for sa, sb, nm in _CH:
        if sa <= s <= sb: return nm
    return None

_ORDER = {"exact": 0, "paren": 1, "alias": 2, "substring": 3, "fuzzy": 4}

def kcd_fields(matches):
    """반환: (kcd_code_primary, kcd_primary_name, kcd_codes_list, categories_list)"""
    if not matches:
        return None, None, [], []
    best = sorted(matches, key=lambda m: _ORDER.get(m.get("match_type"), 9))[0]
    codes, seen, cats = [], set(), []
    for m in matches:
        if m["code"] not in seen:
            seen.add(m["code"]); codes.append(m["code"])
        ch = code_to_chapter(m["code"])
        if ch and ch not in cats: cats.append(ch)
    return best["code"], best.get("korean_name"), codes, cats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    files = sorted(glob.glob(os.path.join(OUTPUT, "*.json")))
    lines = []
    n_doc = n_chunk = n_img_doc = n_cat = n_kcd = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        if d.get("category") != "disease":
            continue
        n_doc += 1
        disease = d["disease"]; sn = d.get("cntnts_sn")
        has_img = bool(d.get("has_image_text"))
        if has_img: n_img_doc += 1

        kcd_code, kcd_name, kcd_codes, cats = kcd_fields(d.get("kcd_matches", []))
        rel = extract_related_diseases(d, primary=disease)   # output 섹션(이미지 병합본) 기준
        if cats: n_cat += 1
        if kcd_code: n_kcd += 1

        for i, (label, body, tbl) in enumerate(chunk_sections(d["sections"])):
            meta = {
                "primary_key": disease,
                "doc_type": "disease",
                "section": label,
                "cntnts_sn": sn,
                "source": d.get("source", ""),
                "source_label": d.get("source_label", ""),
                "review_status": d.get("review_status", ""),
                "created_at": TODAY,
                "has_image_text": has_img,
            }
            # Pinecone: 비면 키 생략(빈배열/null 금지)
            if cats: meta["categories"] = cats
            if kcd_code: meta["kcd_code"] = kcd_code
            if kcd_name: meta["kcd_primary_name"] = kcd_name
            if kcd_codes: meta["kcd_codes"] = kcd_codes
            if rel: meta["related_diseases"] = rel
            if tbl is not None:
                meta["content_type"] = "table"       # 팀원이 파인콘에서 표만 필터/랭킹 조정 가능
                if tbl: meta["table_title"] = tbl
            rec = {"id": f"kdca-{sn}-{i}",
                   "text": f"{disease} - {label}{tbl_prefix(tbl)}\n\n{body}",
                   "metadata": meta}
            lines.append(json.dumps(rec, ensure_ascii=False))
            n_chunk += 1

    with open(args.out, "w", encoding="utf-8") as of:
        of.write("\n".join(lines) + "\n")
    print(f"disease {n_doc}건 -> 청크 {n_chunk}개")
    print(f"  이미지텍스트 포함 문서: {n_img_doc}건")
    print(f"  categories 부여: {n_cat}/{n_doc} | kcd_code 부여: {n_kcd}/{n_doc}")
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
