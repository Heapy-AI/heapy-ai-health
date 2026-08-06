# -*- coding: utf-8 -*-
"""공용 유틸: 섹션 중복 제거, 내용 정제(base64), 이미지 텍스트 병합, 임베디드 질환명 추출."""
import re, os, json

_DATA_URI = re.compile(r"data:[^;,\s]+;base64,[A-Za-z0-9+/=\s]+")

def strip_data_uri(text):
    """본문에 섞인 data:...;base64,... 이미지 블록 제거."""
    return _DATA_URI.sub("", text or "").strip()

def clean_sections(sections):
    """각 섹션 content에서 base64 data URI 제거. 제거 후 빈(10자 미만) 섹션은 버림."""
    out = []
    for s in sections:
        c = strip_data_uri(s.get("content", ""))
        if len(c) >= 10:
            out.append({**s, "content": c})
    return out

def _norm_sec(s): return (s or "").replace(" ", "").strip()

def load_image_extractions(path):
    """gemini OCR 결과(extractions.json) -> {(sn, norm섹션): [info텍스트,...] (order순)}, n_info."""
    if not path or not os.path.exists(path):
        return {}, 0
    data = json.load(open(path, encoding="utf-8"))
    grouped = {}; n = 0
    for v in sorted(data.values(), key=lambda x: (str(x.get("sn")), x.get("order", 0))):
        if v.get("kind") != "info" or not (v.get("text") or "").strip():
            continue
        n += 1
        grouped.setdefault((str(v.get("sn")), _norm_sec(v.get("section"))), []).append(v["text"].strip())
    return grouped, n

def inject_image_text(doc, img_by_key):
    """이미지 info 텍스트를 (sn,섹션) 매칭해 섹션 content에 append.
    원문에 없던 섹션(image-only)은 새 섹션으로 추가. 반환:(주입여부, 추가섹션수)."""
    sn = str(doc.get("cntnts_sn")); injected = False; added = 0
    name_idx = {}
    for i, s in enumerate(doc.get("sections", [])):
        name_idx.setdefault(_norm_sec(s.get("name", "")), i)
    for (ksn, ksec), texts in img_by_key.items():
        if ksn != sn:
            continue
        blob = "\n".join(texts)
        if ksec in name_idx:
            s = doc["sections"][name_idx[ksec]]
            s["content"] = (s.get("content", "") + "\n\n[이미지 정보]\n" + blob).strip()
            injected = True
        else:
            doc["sections"].append({"name": ksec, "content": "[이미지 정보]\n" + blob})
            name_idx[ksec] = len(doc["sections"]) - 1
            injected = True; added += 1
    return injected, added


def dedup_sections(sections):
    """(name, content) 완전 동일 쌍의 중복 블록 제거(순서 유지). 반환: (정제섹션, 제거수)."""
    seen=set(); out=[]; removed=0
    for s in sections:
        key=(s.get("name",""), s.get("content",""))
        if key in seen:
            removed+=1; continue
        seen.add(key); out.append(s)
    return out, removed

# 임베디드 질환을 뽑을 섹션명(정규화 공백제거 기준)
EMBED_SECTIONS = {"관련질환","관련증상및질환","동반질환","연관증상"}

# 번호 헤더: "1. 충수염" 또는 "1) 양성돌발성두위현훈(이석증)"
_NUM_HEADER = re.compile(r"(?m)^\s*\d+[\.\)]\s*(.+?)\s*$")
# 콤마/가운뎃점/슬래시로 분할
_SPLIT = re.compile(r"[,，·/、]| 및 | 와 | 과 ")
# 괄호 안 별칭 추출용
_PAREN = re.compile(r"[\(（]([^\)）]+)[\)）]")

# 질환명으로 부적절한 헤더(하위 항목 라벨/카테고리) 필터
_STOP = re.compile(r"(증상|진단|치료|합병증|검사|원인|예방|경과|개요|정의|방법|관리|주의|특성|위치|양상|기타|참고|질문|대처|단계|훈련|현황|영향|효과)$")
# 카테고리 헤더(질환 자체 아님) 필터
_CATEGORY = re.compile(r"(원인|질환군|분류)$")

def _add(out, seen, name, src):
    name = re.sub(r"\s+", " ", (name or "").strip().strip("·-—"))
    if not name or len(name) < 2 or len(name) > 30:
        return
    if _STOP.search(name.replace(" ","")):
        return
    if name in seen:
        return
    seen.add(name)
    out.append({"chunk_name": name, "section_source": src})

# related_diseases 추출용: 종류(하위형)·관련질환·동반질환 섹션
_REL_SECTIONS = {"종류","관련질환","관련증상및질환","동반질환"}
# 연관 주제어에서 질환으로 볼 접미사
_DISEASE_SUFFIX = re.compile(r"(증|염|병|암|증후군|장애|경화증|결핍증|공포증|중독|기형|손상|골절|탈구|종양|낭종|용종|결석|궤양|부전|협착|폐색|출혈|경색|마비)$")

def extract_related_diseases(doc, primary=None):
    """disease 문서에서 하위/연관 질환명 추출.
    - 종류/관련질환/동반질환 섹션의 번호헤더(1. / 1))
    - 연관 주제어 섹션에서 질환접미사로 끝나는 토큰
    표제어(primary) 자신 및 중복은 제외. 반환: [str]."""
    def norm(n): return (n or "").replace(" ", "").strip()
    pk = norm(primary or doc.get("disease",""))
    out=[]; seen=set()
    def add(name):
        name = re.sub(r"\s+", " ", (name or "").strip().strip("·-—()[]"))
        if not name or len(name) < 2 or len(name) > 30: return
        if _STOP.search(name.replace(" ","")): return
        # 카테고리성 노이즈 제거(기타/그 외/다른 종류/각종 …)
        if re.match(r"^(기타|그\s*외|그외|다른|각종|여러|일부)", name): return
        if "종류" in name: return
        key = norm(name)
        if not key or key == pk or key in seen: return
        seen.add(key); out.append(name)
    for s in doc.get("sections", []):
        nm = norm(s.get("name",""))
        content = s.get("content","") or ""
        if nm in _REL_SECTIONS:
            for m in _NUM_HEADER.finditer(content):
                header = m.group(1).strip()
                if len(header) > 30: continue
                aliases = _PAREN.findall(header)
                base = _PAREN.sub("", header).strip()
                for part in _SPLIT.split(base):
                    if _CATEGORY.search(part.replace(" ","")): continue
                    add(part)
                for al in aliases:
                    for part in _SPLIT.split(al): add(part)
        elif nm in ("연관주제어","연관주제"):
            for part in re.split(r"[,，·/、]", content):
                p = part.strip()
                if _DISEASE_SUFFIX.search(p.replace(" ","")):
                    add(p)
    return out


def extract_embedded_diseases(doc):
    """관련질환류 섹션에서 번호 헤더로 나열된 하위 질환명 추출.
    - "1." 및 "1)" 번호 헤더 모두 인식
    - 괄호 안 별칭(예: 양성돌발성두위현훈(이석증))도 별도 후보로 추가
    반환: [{"chunk_name", "section_source"}] (KCD매칭은 상위에서 수행)."""
    def norm(n): return (n or "").replace(" ", "").strip()
    out=[]; seen=set()
    for s in doc.get("sections", []):
        nm = norm(s.get("name",""))
        if nm not in EMBED_SECTIONS:
            continue
        content = s.get("content","") or ""
        src = s.get("name","")
        for m in _NUM_HEADER.finditer(content):
            header = m.group(1).strip()
            if len(header) > 30:
                continue
            # 괄호 안 별칭 먼저 뽑고, 본문에서 괄호 제거
            aliases = _PAREN.findall(header)
            base = _PAREN.sub("", header).strip()
            for part in _SPLIT.split(base):
                if _CATEGORY.search(part.replace(" ","")):
                    continue
                _add(out, seen, part, src)
            for al in aliases:
                for part in _SPLIT.split(al):
                    _add(out, seen, part, src)
    return out
