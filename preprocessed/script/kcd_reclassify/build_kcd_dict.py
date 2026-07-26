# -*- coding: utf-8 -*-
"""KCD-9 마스터파일 -> 한글명칭(대표어+이명) 딕셔너리 생성 + JSON 캐시.

행 규칙(스캔으로 확인):
- 3행 헤더 / 4행부터 데이터. 컬럼: 1표제어 2분류기준 3질병분류코드 4검별 5주석 6한글명칭 7영문명칭 8최하위코드 ...
- 분류기준(대/중/소/세/세세/세세세)이 채워진 행 = 대표어 행.
- 분류기준 공백 + 코드가 직전 행과 동일 = 이명(동의어) 행. -> 같은 코드/레벨에 명칭만 추가.
"""
import openpyxl, json, os, re, io, sys, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
# data/ 폴더에서 KCD-9 마스터파일 자동 탐색(파일명 버전 무관)
_cands = (glob.glob(os.path.join(_ROOT, "data", "*masterfile*.xlsx"))
          or glob.glob(os.path.join(_ROOT, "data", "제9차*.xlsx")))
XLSX = os.environ.get("KCD_MASTERFILE") or (_cands[0] if _cands else "")
OUT  = os.path.join(_HERE, "kcd_dict.json")
if not XLSX or not os.path.exists(XLSX):
    sys.exit("KCD-9 마스터파일을 찾지 못했습니다. data/ 에 두거나 KCD_MASTERFILE 환경변수로 경로를 지정하세요.")

LEVELS = {"대","중","소","세","세세","세세세"}

def strip_paren(s):
    # 괄호(소/중/대) 및 내부설명 제거
    s = re.sub(r"[\(\[\{（【].*?[\)\]\}）】]", "", s)
    return s

def clean_name(s):
    if s is None: return ""
    s = str(s).replace("\n"," ").strip()
    # 코드가 명칭 끝에 붙은 경우 제거: "...(A00-B99)" 형태 등은 strip_paren이 처리
    return s

def norm_key(s):
    """매칭용 정규화 키: 공백제거 + 괄호제거 + 특수기호 정리."""
    s = strip_paren(s)
    s = s.replace(" ", "").strip()
    # 로마숫자 편/장 표시 및 선행 'Ⅰ.' 등 제거
    s = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ0-9]+\.", "", s)
    # 후행 NOS / 상세불명 등은 유지(별도 이명일 수 있음)
    return s.strip()

def main():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["KCD-9 DB Masterfile"]

    # 대분류(챕터) 목록
    chapters = []
    # code -> {level, primary_name}
    code_info = {}
    # normalized_name(괄호제거) -> list of {code, level, korean_name, is_alias}
    name_map = {}
    # raw_key(괄호유지, 공백만제거) -> 동일 엔트리 (exact 판별용)
    raw_map = {}
    n_head = n_alias = 0
    prev_code = None; prev_level = None

    for row in ws.iter_rows(min_row=4, values_only=True):
        pyoje = row[0]        # 표제어 (1이면 대표어)
        gijun = (row[1] or "").strip() if row[1] else ""
        code  = clean_name(row[2])
        kname = clean_name(row[5])
        if not code or not kname:
            # 명칭 없는 행 스킵
            if code: prev_code = code
            continue

        is_head = gijun in LEVELS
        if gijun == "대":
            # 대분류 챕터: 코드=범위(A00-B99), 명칭에서 로마숫자/괄호 제거
            nm = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ0-9IVXivx]+\.?\s*", "", str(kname)).strip()
            nm = re.sub(r"\s*\([A-Z]\d.*?\)\s*$", "", nm).strip()
            rng = str(code).replace(" ", "")
            chapters.append({"range": rng, "name": nm})
        if is_head:
            level = gijun
            code_info.setdefault(code, {"level": level, "primary_name": kname})
            prev_code = code; prev_level = level
            n_head += 1
            is_alias = False
        else:
            # 이명 행: 코드가 직전 코드와 동일하면 그 코드/레벨 상속
            if code == prev_code and prev_level:
                level = prev_level
            else:
                level = code_info.get(code, {}).get("level", "")
                prev_code = code; prev_level = level or prev_level
            n_alias += 1
            is_alias = True

        # 대표 명칭에서 괄호 안 코드표기 제거한 표시용 이름
        disp = strip_paren(kname).strip() or kname
        entry = {"code": code, "level": level, "korean_name": disp, "is_alias": is_alias}
        keys = {norm_key(kname), norm_key(disp)}
        # 대괄호 [ ] 안 동의어(예: '급성 비인두염[감기]' -> 감기)를 별도 키로 등록
        for seg in re.findall(r"\[([^\]]+)\]", str(kname)):
            for part in re.split(r"[,，·]", seg):
                k = norm_key(part)
                if k and len(k) >= 2:
                    keys.add(k)
        for key in keys:
            if not key: continue
            name_map.setdefault(key, [])
            if not any(e["code"]==code and e["is_alias"]==is_alias for e in name_map[key]):
                name_map[key].append(entry)
        # raw_map: 괄호 유지, 공백만 제거한 원본 키 (exact 판별)
        rkey = str(kname).replace(" ", "").strip()
        if rkey:
            raw_map.setdefault(rkey, [])
            if not any(e["code"]==code and e["is_alias"]==is_alias for e in raw_map[rkey]):
                raw_map[rkey].append(entry)

    out = {
        "name_map": name_map,          # norm_key(괄호제거) -> entries
        "raw_map": raw_map,            # 괄호유지 공백제거 키 -> entries
        "code_info": code_info,        # code -> {level, primary_name}
        "chapters": chapters,          # 대분류 22개 {range, name}
        "stats": {"headwords": n_head, "aliases": n_alias, "unique_keys": len(name_map)},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("대표어 행:", n_head, "| 이명 행:", n_alias, "| 고유 정규화키:", len(name_map))
    print("캐시 저장:", OUT)
    # 샘플 확인
    for probe in ["빈혈","철결핍성빈혈","심부전","고혈압","콜레라","당뇨병"]:
        print(f"  '{probe}' ->", name_map.get(probe, "없음"))

if __name__ == "__main__":
    main()
