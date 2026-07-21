# 건강검진 실시기준 전처리

## 범위

현행 `보건복지부고시 제2026-6호`의 다음 공식 PDF를 전처리합니다.

- 별표 1: 일반건강검진 검사항목, 대상자 및 검사방법
- 별표 4: 일반건강검진 및 의료급여생애전환기검진 결과 판정기준
- 별표 4의 별첨: 검사항목별 판정기준

원문은 `storage/source_document/mohw_screening/raw`에 체크섬과 함께 보존합니다.
규정 표는 병합 셀과 복합 논리 조건이 많아 무검수 자동 표 추출을 사용하지 않습니다. PDF
체크섬·페이지 앵커를 자동 확인한 뒤 시각 검수된 규칙 사양으로 JSON과 CSV를 생성합니다.

## 실행

```bash
python3 -m pip install -r requirements-vdb.txt
python3 scripts/preprocess_screening_regulation.py
python3 scripts/preprocess_screening_regulation.py --check
python3 -m unittest tests.test_screening_regulation_preprocessing -v
```

## 산출물

`storage/source_document/mohw_screening/normalized` 아래에 생성됩니다.

- `2026-01-07__MOHW-2026-6__screening-regulation.json`: 전체 규칙과 출처 계보
- `2026-01-07__MOHW-2026-6__screening-items.csv`: 표준 입력 항목
- `2026-01-07__MOHW-2026-6__screening-rules.csv`: 원자·복합 판정 규칙
- `2026-01-07__MOHW-2026-6__screening-eligibility.csv`: 연령·성별 대상 조건
- `2026-01-07__MOHW-2026-6__quality-report.json`: 체크섬·앵커·경계값 검사 결과

규칙의 `expression`은 단일 비교와 `all`, `any`, `not` 조합을 지원합니다. 따라서 수축기와
이완기를 함께 보는 혈압, PHQ-9 9번 문항 우선 규칙, CAPE-15 두 총점, 양쪽 귓속말 검사,
폐기능 조합식을 값 하나로 잘못 평탄화하지 않습니다.

## 운영 제한

- 이 규칙은 국가건강검진 판정용이며 질병 진단 또는 검사실 참고범위가 아닙니다.
- 검진일에 유효한 규칙 버전을 적용하고 과거 결과를 새 규칙으로 덮어쓰지 않습니다.
- 원문이 정의하지 않은 범위는 추정하지 않고 `UNCLASSIFIED`로 처리합니다.
- 규정 개정 시 새 PDF를 별도 보존하고 새 버전 산출물을 생성합니다.
