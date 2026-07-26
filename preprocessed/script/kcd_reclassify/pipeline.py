# -*- coding: utf-8 -*-
"""메인 파이프라인: 재분류 + KCD 매칭 + 임베디드 질환 추출 + 출력.
2패스 구조:
  pass1: 규칙 분류 -> needs_llm 문서를 ambiguous_for_llm.json 으로 방출
  (그 사이 Claude가 llm_verdicts.json 작성)
  pass2: verdict 반영 -> KCD 매칭 -> output/*.json + 통계
"""
import json, os, glob, argparse, re
from classify import classify
from utils import (dedup_sections, clean_sections, extract_embedded_diseases,
                   load_image_extractions, inject_image_text)
from matcher import KCDMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
KDCA = os.path.abspath(os.path.join(HERE, "..", "..", "disease_info", "kdca"))

def before_paren(s):
    i = s.find("("); j = s.find("（")
    ks = [x for x in (i,j) if x>0]
    return s[:min(ks)].strip() if ks else s

_PAREN = re.compile(r"[\(（]([^\)）]+)[\)）]")
# 안전한 구분자만: 및 / 쉼표 / 가운뎃점 / 슬래시 / 공백구분된 와·과
_CONJ = re.compile(r"\s*및\s*|\s*[,，·、/_]\s*|와\s+|과\s+")
# 인구집단/시기 접두어(최후fallback 제거용) — 임상적 의미가 옅은 수식어만
# 인구집단/시기 수식어만(남성/여성/성인 등은 질환명 일부인 경우 많아 제외)
_PREFIX = re.compile(r"^(노인성|노인|소아청소년기|소아청소년|소아|영유아|영아|신생아|청소년)\s*")

def _clean_variant(v):
    v = _PAREN.sub("", v).strip()   # 잔여 괄호 제거
    v = v.strip(" ·-—")
    return v

def query_variants(name):
    """질의어 후보 생성: 전체 / 괄호앞 / 괄호내용 / 접속사 분할 / 접두어제거."""
    name = (name or "").strip()
    variants=[name]
    bp = before_paren(name)
    if bp and bp != name: variants.append(bp)
    for inner in _PAREN.findall(name):
        variants.append(inner)
    # 접속사 분할(전체 및 괄호앞 기준)
    for base in [name, bp] + _PAREN.findall(name):
        for part in _CONJ.split(base):
            p=_clean_variant(part)
            if p and p != name: variants.append(p)
    # 중복 제거(순서 유지)
    seen=set(); out=[]
    for v in variants:
        v=v.strip()
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out

def match_name(matcher, name):
    """다중 variant로 매칭 후 코드 기준 병합. 각 매치에 matched_query 기록."""
    variants = query_variants(name)
    merged=[]; seen_codes=set()
    for v in variants:
        for m in matcher.match(v):
            if m["code"] in seen_codes: continue
            seen_codes.add(m["code"])
            mm=dict(m)
            if v != name.strip():
                mm["matched_query"]=v
            merged.append(mm)
    if merged:
        return merged
    # 최후 fallback: 인구집단 접두어 제거 후 재시도
    stripped = _PREFIX.sub("", name).strip()
    if stripped and stripped != name.strip():
        res=[]
        for m in matcher.match(stripped):
            mm=dict(m); mm["matched_query"]=stripped; res.append(mm)
        return res
    return []

KCD_TARGET = {"disease"}          # 문서 자체 KCD 매칭 대상
EMBED_TARGET = {"symptom","test"} # 임베디드 질환 추출 대상

def process(files, out_dir, matcher, llm_verdicts=None, emit_ambiguous=None, img_by_key=None):
    llm_verdicts = llm_verdicts or {}
    img_by_key = img_by_key or {}
    os.makedirs(out_dir, exist_ok=True)
    records=[]; ambiguous=[]
    for f in files:
        fn = os.path.basename(f)
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        secs, removed = dedup_sections(doc.get("sections", []))
        secs = clean_sections(secs)   # base64 data URI 제거
        doc["sections"] = secs

        # 분류는 텍스트(정제본) 기준으로 먼저 수행(이미지가 분류를 바꾸지 않도록)
        cls = classify(doc)
        orig_super = doc.get("superclass","")
        applied_llm = False
        # LLM verdict 반영
        if fn in llm_verdicts:
            v = llm_verdicts[fn]
            cls["category"] = v["category"]
            cls["category_confidence"] = v.get("confidence","medium")
            cls["category_source"] = "llm:" + v.get("reason","내용판정")
            cls["needs_llm"] = False
            applied_llm = True
        elif cls["needs_llm"] and emit_ambiguous is not None:
            # 애매 문서 -> 방출
            key_secs=[]
            for s in secs:
                nm=s.get("name","")
                key_secs.append({"name":nm, "excerpt": (s.get("content","") or "")[:400]})
            ambiguous.append({
                "file": fn, "disease": doc.get("disease"),
                "superclass": orig_super,
                "rule_category": cls["category"], "rule_source": cls["category_source"],
                "section_names": [s.get("name","") for s in secs],
                "sections": key_secs,
            })

        # 이미지 OCR 텍스트를 canonical 병합(분류 이후 / 임베디드·출력 이전)
        has_img, _ = inject_image_text(doc, img_by_key)

        cat = cls["category"]
        out = dict(doc)  # 기존 필드 그대로(이미지 병합된 sections 포함)
        out["dedup_removed_sections"] = removed
        out["has_image_text"] = has_img
        out["category"] = cat
        out["category_confidence"] = cls["category_confidence"]
        out["category_source"] = cls["category_source"]
        out["kcd_matches"] = []
        out["embedded_disease_chunks"] = []

        # 문서 자체 KCD 매칭 (disease)
        if cat in KCD_TARGET:
            out["kcd_matches"] = match_name(matcher, doc.get("disease",""))
        # 임베디드 질환 추출 + 매칭 (symptom/test)
        if cat in EMBED_TARGET:
            emb = extract_embedded_diseases(doc)
            for e in emb:
                e["kcd_matches"] = match_name(matcher, e["chunk_name"])
            out["embedded_disease_chunks"] = emb

        with open(os.path.join(out_dir, fn), "w", encoding="utf-8") as of:
            json.dump(out, of, ensure_ascii=False, indent=1)

        records.append({
            "file": fn, "disease": doc.get("disease"), "superclass": orig_super,
            "category": cat, "confidence": cls["category_confidence"],
            "source": cls["category_source"], "applied_llm": applied_llm,
            "n_kcd": len(out["kcd_matches"]),
            "kcd_match_types": [m["match_type"] for m in out["kcd_matches"]],
            "n_embedded": len(out["embedded_disease_chunks"]),
            "removed": removed,
            "has_image_text": has_img,
        })

    if emit_ambiguous is not None:
        with open(emit_ambiguous, "w", encoding="utf-8") as af:
            json.dump(ambiguous, af, ensure_ascii=False, indent=1)
        print(f"애매 문서 {len(ambiguous)}건 -> {emit_ambiguous}")
    return records


def load_verdicts(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", help="처리할 파일 basename 목록(미지정시 전체)")
    ap.add_argument("--list-file", help="처리할 basename 목록이 담긴 JSON 파일")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "..", "..", "output"))
    ap.add_argument("--verdicts", default=os.path.join(HERE, "llm_verdicts.json"))
    ap.add_argument("--emit-ambiguous", default=os.path.join(HERE, "ambiguous_for_llm.json"))
    ap.add_argument("--no-emit", action="store_true")
    ap.add_argument("--extractions", default=os.path.join(HERE, "image_ocr", "extractions.json"),
                    help="이미지 OCR 결과(gemini_ocr_images.py). 있으면 섹션에 이미지 텍스트 병합")
    args = ap.parse_args()

    all_files = sorted(glob.glob(os.path.join(KDCA, "*.json")))
    want=None
    if args.list_file:
        with open(args.list_file, encoding="utf-8") as lf:
            want=set(json.load(lf))
    elif args.files:
        want=set(args.files)
    files=[f for f in all_files if os.path.basename(f) in want] if want else all_files

    matcher = KCDMatcher()
    verdicts = load_verdicts(args.verdicts)
    emit = None if args.no_emit else args.emit_ambiguous
    img_by_key, n_img = load_image_extractions(args.extractions)
    if n_img:
        print(f"이미지 OCR 텍스트 병합: {n_img}개 블록 ({len(img_by_key)} 문서·섹션)")
    recs = process(files, os.path.abspath(args.out), matcher, verdicts, emit, img_by_key)

    from collections import Counter
    print("처리:", len(recs), "건")
    print("category:", dict(Counter(r["category"] for r in recs)))
    print("confidence:", dict(Counter(r["confidence"] for r in recs)))
    print("이미지텍스트 병합 문서:", sum(1 for r in recs if r.get("has_image_text")))
