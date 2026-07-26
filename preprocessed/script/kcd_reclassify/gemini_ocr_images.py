# -*- coding: utf-8 -*-
"""KDCA 건강정보 이미지 → Gemini 멀티모달 OCR → extractions.json

원본 XML(_kdca_raw_xml)의 이미지/첨부 URL(cntntsCl의 CNTNTS_CL_CN가 순수 URL인 블록)을
대상 섹션 기준으로 모아 내려받고, Gemini로 표/기준/수치 등 텍스트 정보를 추출한다.
결과는 downstream 통합 스크립트(integrate_image_text.py)가 쓰는 포맷으로 저장.

────────────────────────────────────────────────────────────
설치:
    pip install google-genai pillow requests
환경변수:
    export GEMINI_API_KEY=<your-key>        # (Windows) set GEMINI_API_KEY=...
실행:
    python gemini_ocr_images.py                       # 기본: disease 카테고리 + 정보밀도 섹션
    python gemini_ocr_images.py --scope all           # 전체 카테고리 전체 섹션
    python gemini_ocr_images.py --sections "종류,진단 및 검사"   # 섹션 직접 지정
    python gemini_ocr_images.py --model gemini-2.5-flash --sleep 0.5
    (중단해도 extractions.json 을 읽어 이어서 진행 = resumable)
출력:
    <이 스크립트 폴더>/image_ocr/extractions.json   # {file: {sn,disease,section,kind,text,url}}
    <이 스크립트 폴더>/image_ocr/img/*.jpg          # 다운로드·다운스케일 캐시
────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import argparse, io, json, os, re, ssl, sys, time, glob
import xml.etree.ElementTree as ET

import requests, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from PIL import Image

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
XMLDIR = os.path.join(ROOT, "preprocessed", "disease_info", "_kdca_raw_xml")
OUTPUT_JSON = os.path.join(ROOT, "output")            # 카테고리 조회용(재분류 결과)
WORK = os.path.join(HERE, "image_ocr")
IMGDIR = os.path.join(WORK, "img")
EXF = os.path.join(WORK, "extractions.json")

FILE_URL = re.compile(r"^\s*https?://\S+\s*$")
MAXDIM = 1600

# 기본 대상 섹션(정보밀도 높은 곳) — --sections 로 덮어쓰기 가능
DEFAULT_SECTIONS = [
    "진단 및 검사", "검사 결과 해석", "검사 항목", "검사 목적", "검사 절차", "검사 준비",
    "평가 및 검사", "검사 적응증 및 금기증", "검사 검체", "검사 장비",
    "치료", "약물 치료", "비약물 치료", "치료 방법", "치료의 적응증", "치료 후 관리", "치료 관련 검사",
    "종류", "대상별 맞춤 정보",
]

PROMPT = (
    "당신은 의료 건강정보 그림/표에서 텍스트 정보를 추출하는 OCR·정리 도우미입니다.\n"
    "이 이미지는 질병관리청 국가건강정보포털 '{disease}' 문서의 '{section}' 섹션에 실린 그림 또는 표입니다.\n"
    "아래 JSON 스키마로만 답하세요(다른 설명 금지):\n"
    '{{"kind":"info|illus","text":"..."}}\n'
    "- kind=\"info\": 표, 분류, 진단·검사 기준, 수치/정상범위, 약물 용량, 단계·등급 등 검색·인용 가치가 있는 "
    "텍스트가 이미지에 있을 때. text에 그 내용을 한국어로 충실히 옮겨 적으세요. 표는 행/열을 알아볼 수 있게 정리하고, "
    "제목이 있으면 맨 앞에 [제목] 형태로 넣으세요.\n"
    "- kind=\"illus\": 순수 삽화·해부 모식도·사진이라 옮길 텍스트 정보가 거의 없을 때. "
    "text에는 '[삽화] 무엇을 나타낸 그림인지' 한 줄 요약만.\n"
    "이미지에 실제로 있는 내용만 쓰고, 추측·창작은 금지합니다."
)


class LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **k):
        ctx = create_urllib3_context(); ctx.options |= 0x4
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        k["ssl_context"] = ctx
        return super().init_poolmanager(*a, **k)


def norm(s): return (s or "").replace(" ", "").strip()


def collect_targets(sections, scope):
    """대상 (sn, disease, section, order, url) 목록 생성."""
    # 카테고리/질환명 조회
    cat_of, disease_of = {}, {}
    for f in glob.glob(os.path.join(OUTPUT_JSON, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        cat_of[str(d.get("cntnts_sn"))] = d.get("category")
        disease_of[str(d.get("cntnts_sn"))] = d.get("disease")

    target_secs = {norm(s) for s in sections}
    items = []
    for xf in sorted(glob.glob(os.path.join(XMLDIR, "*.xml"))):
        sn = os.path.basename(xf).replace(".xml", "")
        if scope == "target" and cat_of.get(sn) != "disease":
            continue
        try:
            root = ET.fromstring(open(xf, "rb").read())
        except Exception:
            continue
        sec_ord = {}
        for cl in root.iter("cntntsCl"):
            nm = (cl.findtext("CNTNTS_CL_NM") or "").strip()
            cn = (cl.findtext("CNTNTS_CL_CN") or "").strip()
            if not (cn and FILE_URL.match(cn)):
                continue
            if scope == "all" or norm(nm) in target_secs:
                k = sec_ord.get(nm, 0); sec_ord[nm] = k + 1
                items.append({"sn": sn, "disease": disease_of.get(sn, "?"),
                              "section": nm, "order": k, "url": cn,
                              "category": cat_of.get(sn, "?")})
    return items


def fetch_image(sess, url, fp):
    """다운로드 → RGB 다운스케일 → jpg 저장. 성공 시 True."""
    if os.path.exists(fp):
        return True
    b = None
    for attempt in range(3):
        try:
            b = sess.get(url, timeout=40, verify=False).content; break
        except Exception:
            time.sleep(0.8)
    if not b:
        return False
    try:
        im = Image.open(io.BytesIO(b)).convert("RGB")
        w, h = im.size
        if max(w, h) > MAXDIM:
            s = MAXDIM / max(w, h); im = im.resize((int(w * s), int(h * s)))
        im.save(fp, "JPEG", quality=85)
        return True
    except Exception:
        return False


def make_client(api_key, model):
    """google-genai 우선, 없으면 google-generativeai 로 폴백. (call(bytes)->text) 반환."""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)

        def call(jpg_bytes, prompt):
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg"), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            return resp.text
        return call
    except Exception:
        import google.generativeai as genai  # 폴백(구 SDK)
        genai.configure(api_key=api_key)
        gm = genai.GenerativeModel(model)

        def call(jpg_bytes, prompt):
            resp = gm.generate_content(
                [{"mime_type": "image/jpeg", "data": jpg_bytes}, prompt],
                generation_config={"response_mime_type": "application/json", "temperature": 0},
            )
            return resp.text
        return call


def parse_json(txt):
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.I | re.M).strip()
    try:
        obj = json.loads(txt)
        kind = "info" if obj.get("kind") == "info" else "illus"
        return kind, str(obj.get("text", "")).strip()
    except Exception:
        return "info", txt   # 파싱 실패 시 원문 보존


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["target", "all"], default="target",
                    help="target=disease 카테고리+정보밀도섹션(기본), all=전체")
    ap.add_argument("--sections", default="", help="쉼표구분 섹션명(지정 시 DEFAULT_SECTIONS 대체)")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--sleep", type=float, default=0.5, help="호출 간 대기(초), RPM 한도 대응")
    ap.add_argument("--limit", type=int, default=0, help="테스트용 처리 개수 제한(0=전체)")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("환경변수 GEMINI_API_KEY 가 필요합니다.", file=sys.stderr); return 2

    os.makedirs(IMGDIR, exist_ok=True)
    sections = [s.strip() for s in args.sections.split(",") if s.strip()] or DEFAULT_SECTIONS
    items = collect_targets(sections, args.scope)
    print(f"대상 이미지: {len(items)}개 (scope={args.scope}, 섹션 {len(sections)}종)")

    data = json.load(open(EXF, encoding="utf-8")) if os.path.exists(EXF) else {}
    sess = requests.Session()
    sess.mount("https://", LegacyAdapter()); sess.mount("http://", LegacyAdapter())
    call = make_client(api_key, args.model)

    ok = skip = fail = 0
    processed = 0
    for it in items:
        safe = re.sub(r"[^가-힣A-Za-z0-9]+", "", it["section"]) or "none"
        fn = f"{it['sn']}_{safe}_{it['order']}.jpg"
        if fn in data:
            skip += 1; continue
        fp = os.path.join(IMGDIR, fn)
        if not fetch_image(sess, it["url"], fp):
            data[fn] = {**it, "kind": "fail", "text": "", "file": fn}
            fail += 1
        else:
            try:
                raw = call(open(fp, "rb").read(),
                           PROMPT.format(disease=it["disease"], section=it["section"]))
                kind, text = parse_json(raw)
                data[fn] = {"sn": it["sn"], "disease": it["disease"], "section": it["section"],
                            "order": it["order"], "url": it["url"], "file": fn,
                            "kind": kind, "text": text}
                ok += 1
            except Exception as e:
                data[fn] = {**it, "kind": "fail", "text": f"ERR:{str(e)[:80]}", "file": fn}
                fail += 1
            time.sleep(args.sleep)
        processed += 1
        if processed % 25 == 0:
            json.dump(data, open(EXF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  진행 {processed}/{len(items)} (ok {ok}, skip {skip}, fail {fail})", flush=True)
        if args.limit and processed >= args.limit:
            break

    json.dump(data, open(EXF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    info = sum(1 for v in data.values() if v.get("kind") == "info")
    illus = sum(1 for v in data.values() if v.get("kind") == "illus")
    print(f"\n완료: 누적 {len(data)}개 (info {info}, illus {illus}, fail {fail}) -> {EXF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
