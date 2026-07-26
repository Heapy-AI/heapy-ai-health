# KDCA 건강정보 재분류 + KCD-9 매칭 + disease VDB 빌드

질병관리청 국가건강정보포털 건강정보(650건)를 **7개 카테고리로 재분류**하고, 질환 문서를
**KCD-9 코드에 매칭**한 뒤, 이미지 속 표/기준 텍스트까지 병합해 **Pinecone용 disease VDB 청크**를 만든다.

> ⚠️ **데이터는 git에 포함되지 않는다.** 아래 "필요한 입력 데이터"를 직접 준비해야 실행된다.
> 스크립트/코드만 git에 있으며, 모든 경로는 상대경로라 어느 환경에서도 동작한다.

---

## 0. 카테고리 (재분류 결과)
`disease`(질환) · `symptom`(증상) · `test`(검사방법) · `procedure`(시술·치료법) ·
`lifestyle`(생활습관) · `environmental`(환경보건) · `service`(행정·제도)
- KCD-9 매칭 대상 = `disease` 문서 + `symptom`/`test` 문서의 임베디드 질환
- 자세한 정의·통계는 실행 후 생성되는 `output/_reports/summary_report.md` 참고

---

## 1. 환경 준비

```bash
# Python 3.11 가상환경 (이 프로젝트는 루트의 health-ai/ 사용, 3.11.9)
python -m venv .venv && source .venv/Scripts/activate   # (Windows Git Bash 기준)

# 의존 패키지
pip install openpyxl rapidfuzz requests transformers pillow
pip install google-genai          # 이미지 OCR(선택 단계)에서만 필요
```
- `transformers`는 청킹 시 토크나이저(`jhgan/ko-sroberta-multitask`, 768차원·max 128토큰)를
  최초 1회 자동 다운로드한다(인터넷 필요).

## 2. 필요한 입력 데이터 (git 미포함 — 직접 배치)

| 파일 | 위치 | 필요 단계 |
|---|---|---|
| KCD-9 마스터파일 `*.xlsx` (예: `제9차 …masterfile….xlsx`) | `data/` | build_kcd_dict |
| KDCA API URL 목록 `*국가건강정보포털*API*.xlsx` | `data/disease_info/` | preprocess (원천 수집) |
| (또는) 전처리 완료본 `*.json` 650건 | `preprocessed/disease_info/kdca/` | pipeline 입력 |
| (캐시) 원본 XML | `preprocessed/disease_info/_kdca_raw_xml/` | preprocess 재실행 가속 |

**진입 방식 2가지**
- **A. 원천부터**: `data/disease_info`에 API xlsx를 두고 `preprocess_kdca.py` 실행 → 650 JSON 생성
  (XML 캐시가 있으면 네트워크 재요청 없이 캐시에서 재파싱)
- **B. 전처리본부터**: 이미 `preprocessed/disease_info/kdca/*.json`(650건)을 받았다면 preprocess 생략하고 3단계부터 시작

> 모든 명령은 **이 폴더(`preprocessed/script/kcd_reclassify/`)에서** 실행하면 된다(경로는 스크립트 기준 자동 계산).

---

## 3. 실행 순서

```bash
cd preprocessed/script/kcd_reclassify

# (A 진입 시에만) ① 원천 XML → 전처리 JSON 650건
python ../preprocess_kdca.py
#   → preprocessed/disease_info/kdca/*.json  (+ _kdca_raw_xml/ 캐시)

# ② KCD-9 딕셔너리 생성 (대표어+이명, 대분류 챕터 포함)
python build_kcd_dict.py
#   → kcd_dict.json   (data/ 의 마스터파일 자동 탐색; KCD_MASTERFILE 환경변수로 경로 지정도 가능)

# ③ 재분류 + KCD 매칭 (+ base64 제거, 이미지텍스트 병합)
python pipeline.py --no-emit
#   → output/*.json  650건 (category/kcd_matches/embedded_disease_chunks/has_image_text 등 추가)
#   * llm_verdicts.json(애매 57건 판정결과)은 repo에 포함되어 자동 사용됨

# ④ 요약 리포트/CSV
python report.py
#   → output/_reports/  summary_report.md, mismatch_review.csv, unmatched_kcd.csv, low_confidence.csv

# ⑤ disease VDB 청크 생성 (Pinecone 스키마)
python integrate_and_build_vdb.py
#   → vdb/chunk/disease_info/kdca_disease_enriched.jsonl
```

기대 결과(정상): 전처리 650건 → 재분류 `disease 430 / lifestyle 59 / test 57 / procedure 55 /
environmental 33 / symptom 9 / service 7`, disease KCD 매칭 ≈ 268/430, VDB ≈ 15,000청크.

---

## 4. (선택) 이미지 속 텍스트 OCR 병합

건강정보 그림/표(예: 검사 종류표, 질환 분류표)에는 본문에 없는 임상정보가 있다.
Gemini 멀티모달로 OCR해 섹션에 병합할 수 있다.

```bash
export GEMINI_API_KEY=<your-key>              # Windows: set GEMINI_API_KEY=...

# ⓐ 이미지 다운로드 + OCR (기본: disease + 정보밀도 섹션 ≈ 814장)
python gemini_ocr_images.py --limit 20        # 먼저 20장으로 품질 확인 권장
python gemini_ocr_images.py                   # 전량
#   → image_ocr/extractions.json  (kind=info/illus/fail)
#   옵션: --scope all(전체 2742장) / --sections "종류,진단 및 검사,..." / --model gemini-2.5-flash / --sleep

# ⓑ 병합해서 ③~⑤ 재실행 (extractions.json 을 자동 인식해 섹션에 [이미지 정보]로 병합)
python pipeline.py --no-emit --extractions image_ocr/extractions.json
python report.py
python integrate_and_build_vdb.py
```
- `pipeline.py`는 항상 원본(전처리본)을 다시 읽어 병합하므로 **재실행해도 중복 병합 없음(idempotent)**.
- OCR 없이 ③을 돌리면 이미지 없이(단, base64는 제거된) 텍스트 빌드가 나온다.

---

## 5. 파일 역할

| 파일 | 역할 |
|---|---|
| `build_kcd_dict.py` → `kcd_dict.json` | KCD-9 명칭(대표어+이명)→{코드,레벨} 딕셔너리 + 대분류 22챕터 |
| `classify.py` | 7카테고리 규칙 분류(섹션 구성/제목 기반) |
| `matcher.py` | KCD 매칭(exact→paren→alias→substring→fuzzy) |
| `utils.py` | 섹션 dedup, base64 제거, 이미지텍스트 병합, 임베디드/연관질환 추출 |
| `pipeline.py` | 재분류+매칭+병합 실행 → `output/` |
| `llm_verdicts.json` | 규칙으로 애매한 57건의 내용판정 결과(입력) |
| `report.py` | 요약 리포트/CSV |
| `gemini_ocr_images.py` | (선택) 이미지 Gemini OCR → `image_ocr/extractions.json` |
| `integrate_and_build_vdb.py` | `output/` → Pinecone 스키마 VDB 청크 |

## 6. 산출물 / VDB 스키마

`vdb/chunk/disease_info/kdca_disease_enriched.jsonl` — 한 줄 = 청크 1개:
```json
{
  "id": "kdca-3828-0",
  "text": "심부전 - 개요 / 정의\n\n...",
  "metadata": {
    "primary_key": "심부전", "doc_type": "disease",
    "categories": ["순환계통의 질환"],
    "kcd_code": "I50", "kcd_primary_name": "심부전", "kcd_codes": ["I50"],
    "related_diseases": ["심근경색","협심증"],
    "section": "개요 / 정의", "cntnts_sn": 3828,
    "source": "...", "source_label": "질병관리청 국가건강정보포털",
    "review_status": "SOURCE_VERIFIED", "created_at": "YYYY-MM-DD",
    "has_image_text": false
  }
}
```
- 임베딩: `jhgan/ko-sroberta-multitask` (768차원, cosine) — Pinecone 인덱스도 768/cosine으로 생성
- metadata는 Pinecone 규칙(문자열/숫자/불리언/문자열배열)만 사용. **값이 없으면 키 자체를 생략**(null·빈배열 금지)
- Pinecone 적재(ingest)는 백엔드 코드에서 수행

## 7. 알려진 사항
- **base64 이미지 오염**: 원본에 이미지가 본문 텍스트로 박힌 1건(간선종)은 `pipeline.py`가 자동 제거.
  원본 입력(`preprocessed/…/kdca/*.json`)은 보존되며 제거는 output/VDB 단계에서 적용.
- **청크 128토큰 초과**: `chunk_disease.py` 프리픽스가 토큰예산에 미포함이라 일부 청크가 128을 살짝 넘어
  임베딩 시 꼬리가 잘릴 수 있음(전 컬렉션 공통 특성). 필요 시 `BUDGET` 하향 튜닝.
- **미매칭 KCD**: KCD 미수록 구어체(노안·생리통 등)는 `unmatched_kcd.csv`로 남김(임베딩 동의어 매칭이 향후 개선점).
