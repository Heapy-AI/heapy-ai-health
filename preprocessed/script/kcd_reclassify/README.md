# KDCA 건강정보 재분류 + KCD-9 매칭 + disease VDB 빌드

질병관리청 국가건강정보포털 건강정보(650건)를 **7개 카테고리로 재분류**하고, 질환 문서를
**KCD-9 코드에 매칭**한 뒤, 표·기준·이미지 속 텍스트는 선택적 OCR 단계에서 섹션에 병합해 **Pinecone용 disease VDB 청크**를 만든다.

> ⚠️ **대용량 원천 데이터는 git에 포함되지 않는다.** 아래 "필요한 입력 데이터"를 직접 준비해야 실행된다.
> 모든 경로는 상대경로라 어느 환경에서도 동작한다.
>
> 🔁 **재현성**: 파이프라인은 런타임에 LLM을 호출하지 않으므로 완전 결정적이다(같은 입력 2회 실행 →
> 650개 산출물 SHA-256 동일 확인). 단 아래 3개 파일이 **함께 커밋되어야** 같은 결과가 나온다.
> 빠지면 규칙 분류만 돌아가 결과가 달라진다(예: `두근거림`이 symptom → disease로 되돌아감).
>
> | 파일 | 크기 | 없으면 |
> |---|---|---|
> | `llm_verdicts.json` | ~16KB | 내용 판정 82건 소실 → 카테고리 다수 변경 |
> | `kcd_overrides.json` | ~2KB | KCD 오매칭 4건 재발 |
> | `kcd_dict.json` | ~20MB | 매칭 전부 불가. 재생성에는 `data/`의 KCD 마스터파일 xlsx 필요 |
>
> 의존성 `rapidfuzz`는 루트 `requirements.txt`에 없다. 별도 설치가 필요하며, fuzzy 매칭 결과의
> 버전 간 동일성을 보장하려면 버전 고정을 권장한다(검증 환경: `rapidfuzz 3.14.5` / Python 3.11.9).

---

## 0. 카테고리 (재분류 결과)
`disease`(질환) · `symptom`(증상) · `test`(검사방법) · `procedure`(시술·치료법) ·
`lifestyle`(생활습관) · `environmental`(환경보건) · `service`(행정·제도)
- KCD-9 매칭 대상 = `disease` 문서 + **`symptom` 문서** + `symptom`/`test` 문서의 임베디드 질환
  - KCD `R00-R99`가 증상·징후 및 검사 이상소견 전용 章이라 증상 문서의 자체 매칭도 유효하다
    (`두근거림`→R00.2, `두통`→R51). 이 때문에 symptom 매칭률이 disease보다 높다
- **`disease` / `symptom` 경계**: 치료 섹션 유무는 기준이 아니다. 표제어가 확정 진단명인지, 그리고
  치료 내용이 그 자체를 겨냥하는지 원인 질환으로 위임되는지로 판정한다
  (치료 섹션 없는 disease 28건 / 치료 섹션 있는 symptom 20건)
- **`symptom_kind`** (symptom 문서에만 부여): 검사·검체로만 확인되는 이상소견은 `lab_finding`,
  자각·관찰 가능한 증상·징후는 `clinical`. KCD `R70-R94` 대역을 1차 신호로 쓰고
  실제 인지 가능성과 어긋나는 문서는 본문 검토로 덮어쓴다(`symptom_kind_source`에 근거 기록)
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
| (캐시) 원본 XML | `preprocessed/disease_info/_kdca_raw_xml/` | preprocess 재실행 가속 및 OCR/이미지 URL 참조 |

**진입 방식 2가지**
- **A. 원천부터**: `data/disease_info`에 API xlsx를 두고 `preprocess_kdca.py` 실행 → 650 JSON 생성
  (XML 캐시가 있으면 네트워크 재요청 없이 캐시에서 재파싱)
- **B. 전처리본부터**: 이미 `preprocessed/disease_info/kdca/*.json`(650건)을 받았다면 preprocess 생략하고 3단계부터 시작

> 모든 명령은 **이 폴더(`preprocessed/script/kcd_reclassify/`)에서** 실행하면 된다(경로는 스크립트 기준 자동 계산).
>
> 참고: 현재 기본 전처리 흐름에서는 HTML 표를 본문에 직접 풀어넣지 않고 `[표 생략]`으로 축약한다. 표/기준 텍스트는 선택적 OCR 단계에서만 섹션에 병합된다.

---

## 3. 실행 순서

```bash
cd preprocessed/script/kcd_reclassify

# (A 진입 시에만) ① 원천 XML → 전처리 JSON 650건
python ../preprocess_kdca.py
#   → preprocessed/disease_info/kdca/*.json  (+ _kdca_raw_xml/ 캐시)
#   ※ HTML 표는 전처리 단계에서 [표 생략]으로 축약되며, 표/기준 텍스트는 이후 OCR 단계에서만 병합된다.

# ② KCD-9 딕셔너리 생성 (대표어+이명, 대분류 챕터 포함)
python build_kcd_dict.py
#   → kcd_dict.json   (data/ 의 마스터파일 자동 탐색; KCD_MASTERFILE 환경변수로 경로 지정도 가능)

# ③ 재분류 + KCD 매칭 (+ base64 제거, 이미지텍스트 병합)
python pipeline.py --no-emit
#   → output/*.json  650건
#     추가 필드: category / category_confidence / category_source / kcd_matches /
#               embedded_disease_chunks / has_image_text /
#               symptom_kind + symptom_kind_source (symptom 문서만) /
#               kcd_override_reason (예외 적용 문서만)
#   * llm_verdicts.json(내용 판정 82건)과 kcd_overrides.json(KCD 예외 4건)을 자동으로 읽어 적용
#     경로 교체: --verdicts <path> / --overrides <path>

# ④ 요약 리포트/CSV
python report.py
#   → output/_reports/  summary_report.md, mismatch_review.csv, unmatched_kcd.csv, low_confidence.csv

# ⑤ disease VDB 청크 생성 (Pinecone 스키마)
python integrate_and_build_vdb.py
#   → vdb/chunk/disease_info/kdca_disease_enriched.jsonl
```

기대 결과(정상): 전처리 650건 → 재분류 `disease 411 / lifestyle 59 / test 57 / procedure 55 /
environmental 33 / symptom 28 / service 7`, confidence `high 571 / medium 73 / low 6`.
KCD 매칭은 disease 248/411(60.3%), symptom 28/28(100%), 임베디드 30/81.

> ⚠️ `vdb/chunk/.../kdca_disease_enriched.jsonl`이 이미 있다면 **구버전일 수 있다.**
> 현재 저장된 산출물은 430 문서·15,034청크로, 재분류 이전(disease 430) 기준이다.
> 위 숫자(disease 411)와 맞추려면 ⑤단계를 다시 실행해야 한다.

---

## 4. (선택) 이미지 속 텍스트 OCR 병합

건강정보 그림/표(예: 검사 종류표, 질환 분류표)에는 본문에 없는 임상정보가 있다.
기본 전처리 단계에서는 표를 본문에 직접 풀어넣지 않고 `[표 생략]`으로 축약하며,
Gemini 멀티모달 OCR로 추출한 표·기준 텍스트를 섹션에 병합할 수 있다.

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
| `llm_verdicts.json` | 규칙으로 판정이 애매한 82건의 내용판정 결과(입력). `{파일명: {category, confidence, reason}}` |
| `kcd_overrides.json` | KCD 오매칭/미매칭 문서의 대체 질의어 테이블(입력). `{파일명: {queries, reason}}` |
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
- **matcher substring 계층은 휴리스틱이다 — 전역 규칙을 바꾸지 말 것.** 두 가지를 실측했고 둘 다 기각했다.
  - 최소길이 완화(`_substring_candidates`의 `len<3` 가드를 2로): 미매칭 348→306으로 줄지만 2자 조각이
    열려 59문서가 오염된다(`소아`→F65.4 소아성애증, `성인`→F60.3 성격장애, `운동`→G24).
    이 가드 때문에 `복통`·`치통` 같은 2자 진단명이 매칭되지 않는다 — 개별 예외로 처리했다.
  - PRIMARY 이름 우선(alias보다 대표어를 먼저 랭크): 24건 개선 ↔ 23건 악화로 상쇄된다.
    `중이염`→H65는 정답이 되지만 `인플루엔자`가 J09/J10/J11을 잃고 J14(헤모필루스 폐렴)를 얻고,
    `뇌졸중`이 I64를 잃는다.
  - 결론: 개별 문서를 `kcd_overrides.json`에 등록한다. 현재 4건(복통·실어증·치통 2건).
- **`분비물` 류 일반 명사 조각**: 제목 분할로 생긴 `분비물`·`통증` 같은 일반 명사를 단독 질의하면
  해부학적 수식어가 붙은 엉뚱한 코드에 붙는다(`귀의 통증 및 분비물`의 `분비물` → 유두분비물 N64.5,
  요도분비물 R36). `pipeline.py`의 `_GENERIC_FRAGMENT`가 조각일 때만 차단한다(문서명 전체이면 통과).
- **중복 원본 문서**: 같은 주제가 2건씩 있는 경우가 있다(`부종`/`노인 부종`, `어지럼`/`노인 어지럼증`,
  `치통 및 만성 통증` 2건). VDB 적재 시 중복 청크가 되므로 필요하면 상위에서 dedup할 것.
- **임베디드 질환 추출 한계**: `utils.py`의 `_NUM_HEADER`가 번호 목록(`1.`, `1)`)만 인식하므로
  `관련 질환` 섹션이 산문형이면 추출되지 않는다(symptom 28건 중 6건에서만 작동).
