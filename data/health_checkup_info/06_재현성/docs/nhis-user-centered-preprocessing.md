# 건강관리 앱 사용자 관점 전처리

## 결론

첨부 자료를 앱에 넣을 때는 한 테이블로 합치지 않습니다.

| 자료 | 앱에서의 역할 | 사용자 노출 | 금지 사항 |
|---|---|---:|---|
| 일반건강검진 결과통보서 | 내 결과·추적관리·생활습관 처방의 입력 스키마 | 예 | 주민등록번호 원문 저장, 미확인 OCR 값 확정 표시 |
| 직역별·성별·연령별 건강검진정보 | 공개 코호트 비교 참고값 | 예 | 개인 진단·위험 추론, 판정 인원 합계를 100% 분포로 표시 |
| 건강검진청구항목코드 | 청구·수집 파이프라인 내부 코드 | 아니오 | 개인 검사결과 코드나 판정 기준으로 직접 사용 |
| 건강검진 실시기준 | 검진일 기준 버전 판정 규칙 | 판정 근거만 | 확정 진단·치료 결정, 과거 결과에 최신 규칙 덮어쓰기 |
| 질병관리청 건강검진 안내 | 쉬운 설명과 출처 링크 | 예 | 2026년 현행 판정 규칙의 우선 근거로 사용 |

## 입력과 원본 보존

- NHIS 청구코드 CSV: CP949, SHA-256
  `f346a5609972edc994a1379a0745950a7e4120d62648490594d734ceb916c1d4`
- NHIS 코호트 집계 CSV: CP949, SHA-256
  `c3499e23b515c5e8ca7a449927977ec5dd05cdd2d1050b6b3e5364910c68ddf9`
- 보건복지부 일반건강검진 결과통보서: 4쪽, SHA-256
  `3ab6006ad6a25b5d294dc65f323b669e285b7987d3061755b06fec079d4cab6b`

원본은 다음 위치에 그대로 보존합니다.

- `storage/source_document/nhis_screening/raw`
- `storage/source_document/mohw_screening/raw/2026-01-07__MOHW-2026-6__appendix-6-result-notice.pdf`

## 코호트 집계 전처리

### 행 단위와 키

한 행은 `검진사업년도 × 직역 × 5세 연령대 × 성별`입니다. 자료에는 2022~2023년,
직역 3개, 연령대 15개, 성별 2개가 있어 총 180개 코호트가 있습니다.

앱 기본키는 다음처럼 명시적으로 만듭니다.

```text
2023:EMPLOYEE_INSURED:AGE_40_44:FEMALE
```

### 공란과 0

공공데이터포털 API 설명은 빈칸을 “데이터가 존재하지 않음”으로 정의합니다. 따라서
공백 문자열은 `null / NOT_AVAILABLE`, 실제 숫자 `0`은 `REPORTED_ZERO`로 분리합니다.
공란인 지표는 비율도 계산하지 않습니다.

### 비율

- 수검률 = 수검인원 / 대상인원
- 판정·관리·질환별 참고율 = 해당 인원 / 수검인원

판정·관리 항목은 한 사람이 여러 항목에 중복될 수 있습니다. 180개 코호트 모두에서 주요
판정 실인원 합계가 수검인원을 초과하므로, 이 비율들을 합산하거나 원형·100% 누적 차트로
표시하지 않습니다. 각 비율은 독립 참고값으로 표시합니다.

### 사용자 문구

앱의 비교 화면에는 다음 고지를 함께 둡니다.

> 같은 연도·보험 자격·연령대·성별 집단의 공개 통계입니다. 개인의 검사결과나 진단을
> 뜻하지 않으며, 한 사람이 여러 판정 항목에 중복 집계될 수 있습니다.

## 청구코드 전처리

청구코드는 3,777행이지만 고유 코드는 525개입니다. 동일 코드가 여러 적용연도에 등장하므로
기본키는 `청구항목 기준년도 + 청구항목 코드`입니다. 최신 2024년 행은 243개입니다.

첨부 CSV에는 품질 문제가 있습니다.

- `건강검진유형구분코드` 열은 3,776/3,777행에서 코드명이 중복되어 실제 코드가 아닙니다.
- `건강검진유형상세코드` 열은 모든 행에서 코드 첫 글자와 같아 유형구분코드처럼 보입니다.
- 공식 상세구분코드는 첨부파일에서 신뢰성 있게 복원할 수 없습니다.

따라서 원문 두 필드를 그대로 보존하고, 마지막 필드만 `type_code_normalized`로 분리합니다.
상세코드는 `null`로 남기며 코드 앞 3자는 `code_family_prefix`라는 참고값으로만 제공합니다.
이 테이블은 사용자 결과 화면에 노출하지 않습니다.

## 결과통보서 필드 전처리

결과통보서 1·2·4쪽은 PDF 텍스트와 화면을 함께 확인했습니다. 3쪽 심뇌혈관질환 위험평가는
이미지 기반이라 화면 검수로 필드만 정의했습니다. 총 56개 앱 필드를 다음 원칙으로 분류합니다.

- 성명: 본인 식별 영역에만 보관
- 주민등록번호: 원문 저장 금지
- 검사수치·판정·생활습관: 민감 건강정보로 암호화 보관
- OCR·자유서술: 사용자 확인 전 개인화 기능에 사용 금지
- 심뇌혈관 위험도·심뇌혈관 나이: 검진기관이 산출한 값을 출처와 함께 보존하고, 검증된
  위험모형 없이는 앱에서 재계산하지 않음
- 개인 검진값: VDB 임베딩 금지

종합소견은 여러 칸이 동시에 선택될 수 있으므로 단일 등급으로 강제 변환하지 않고
`OVERALL_RESULT_FLAGS` 코드 목록으로 저장합니다.

## 산출물

`storage/source_document/nhis_screening/normalized`에 다음 파일을 생성합니다.

- `2024-07-31__NHIS__screening-claim-item-code-history.csv`
- `2024-07-31__NHIS__screening-claim-item-code-current.csv`
- `2023-12-31__NHIS__screening-cohort-summary.csv`
- `2023-12-31__NHIS__screening-metrics-long.csv`
- `2023-12-31__NHIS__screening-metric-dictionary.csv`
- `2026-01-07__MOHW-2026-6__result-form-field-dictionary.csv`
- `2026-07-16__health-app-source-role-matrix.csv`
- `2026-07-16__health-app-user-data-contract.json`
- `2026-07-16__NHIS-user-centered-quality-report.json`

## 실행과 검증

```bash
python3 -m pip install -r requirements-vdb.txt
python3 scripts/preprocess_nhis_screening.py
python3 scripts/preprocess_nhis_screening.py --check
python3 -m unittest tests.test_nhis_screening_preprocessing -v
```

`--check`는 원본 체크섬, 180개 코호트의 완전한 조합, 복합키 유일성, 수검인원 범위,
공란 보존, 판정 중복성, PDF 쪽수·텍스트 앵커와 생성 파일 동기화를 확인합니다.

## 공식 근거

- 건강검진 실시기준: <https://law.go.kr/LSW/admRulLsInfoP.do?admRulId=38208&efYd=0>
- 질병관리청 건강검진 안내: <https://health.kdca.go.kr/healthinfo/biz/health/ntcnInfo/healthSourc/thtimtCntnts/thtimtCntntsView.do?thtimt_cntnts_sn=7>
- NHIS 청구항목코드: <https://www.data.go.kr/data/15132486/fileData.do>
- NHIS 직역·성별·연령별 집계: <https://www.data.go.kr/data/15144521/fileData.do>

