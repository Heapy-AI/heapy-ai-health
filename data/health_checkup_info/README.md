# 건강검진 데이터 공유 패키지

> **INTERNAL REVIEW — NOT FOR CLINICAL USE**  
> 팀 데이터 검토와 앱 MVP 설계용입니다. 질병 확정 진단, 치료 추천, 응급도 판단 또는 실서비스 자동판정 승인 자료가 아닙니다.

## 먼저 볼 파일

1. [`01_보고서/health-screening-preprocessing-report.html`](01_보고서/health-screening-preprocessing-report.html): 전처리 결과, 앱 사용 경계, 판정기준, 품질 이슈와 공식 출처를 정리한 self-contained HTML 보고서
2. [`02_통합엑셀/health-screening-user-centered-preprocessed.xlsx`](02_통합엑셀/health-screening-user-centered-preprocessed.xlsx): 팀 검토용 통합 엑셀
3. [`03_전처리데이터/NHIS/2026-07-16__health-app-user-data-contract.json`](03_전처리데이터/NHIS/2026-07-16__health-app-user-data-contract.json): 개인결과·집계·청구코드·판정규칙·설명 콘텐츠의 역할과 금지 용도
4. [`04_품질검증/2026-07-16__NHIS-user-centered-quality-report.json`](04_품질검증/2026-07-16__NHIS-user-centered-quality-report.json): NHIS 데이터 품질검증 결과
5. [`04_품질검증/2026-01-07__MOHW-2026-6__quality-report.json`](04_품질검증/2026-01-07__MOHW-2026-6__quality-report.json): 건강검진 판정규칙 품질검증 결과

## 패키지 상태

| 항목 | 상태 | 기준·범위 |
|---|---|---|
| 보건복지부 판정규칙 | 기본 규칙 검증 통과 | 제2026-6호, 2026-01-07 시행 · 43개 항목 · 104개 규칙 · 17개 경계 사례 |
| 사용자용 핵심 해석표 | 검수 완료 | 혈압·비만·빈혈·혈당·지질·간·신장 15개 항목 |
| NHIS 집계 | 경고 포함 통과 | 2022~2023년 · 180개 코호트 · 5,400개 장기형 행 · 공란 428개 |
| 청구코드 | 내부 매핑용 | 2001~2024년 이력 3,777행 · 최신 2024년 243행 |
| VDB 설명 코퍼스 | 개발·단순 설명용 | 30개 SOURCE_VERIFIED 청크 · 임상검수 대기 |
| 자동 테스트 | 통과 | 전체 32개 테스트 통과 |

## 실서비스 배포 전 차단 항목

1. 당뇨병 동반 시 LDL-C 100 mg/dL 미만 및 의사 수정 가능 예외를 실제 조건부 규칙으로 구현해야 합니다.
2. VDB 설명문 30개를 가정의학과 또는 검진의학 의료진이 검수하고 승인 상태를 기록해야 합니다.
3. 검사기관별 PDF/OCR 템플릿, 단위 변환, 기관 참고치와 공식판정 충돌을 end-to-end 테스트해야 합니다.
4. 개인 건강정보의 암호화, 접근권한, 동의, 보유기간, 삭제와 감사로그를 운영 환경에서 검증해야 합니다.
5. 응급·긴급 알림과 치료·재검 권고는 국가검진 판정표와 분리된 임상근거 및 의료진 승인 후 도입해야 합니다.

## 폴더 구성

- `01_보고서`: 공유용 HTML 보고서와 재생성용 artifact/notes JSON
- `02_통합엑셀`: 비개발자와 분석가가 함께 검토할 수 있는 통합 엑셀
- `03_전처리데이터`: NHIS 정규화 데이터, 보건복지부 판정규칙, VDB 코퍼스·평가질문
- `04_품질검증`: 데이터·규칙·VDB 품질 및 검색 회귀평가 결과
- `05_원본근거`: 전처리에 사용한 공식 CSV·PDF 원본
- `06_재현성`: 전처리 스크립트, 테스트, requirements와 방법 문서
- `파일목록_SHA256.txt`: 패키지 파일별 무결성 체크섬

## 데이터 사용 경계

- 결과통보서 스키마와 판정규칙은 개인 검진결과의 구조화·참고 설명에 사용할 수 있습니다.
- NHIS 코호트 집계는 **2022~2023년 역사적 비교자료**이며 현재의 개인 정상범위나 진단 기준이 아닙니다.
- 청구항목 코드는 검진기관의 비용 청구·확인용 내부 코드이며 사용자 검사결과로 노출하지 않습니다.
- 정상A·정상B·질환의심은 국가건강검진 선별 분류이며 질병 확정 진단이 아닙니다.
- 공란은 `0`이 아니라 `NOT_AVAILABLE`로 유지하고, 중복 가능한 판정 인원을 100% 구성비로 합산하지 않습니다.

## 공식 출처

- 보건복지부 건강검진 실시기준 제2026-6호: <https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000272270&chrClsCd=010201>
- 질병관리청 건강검진 안내: <https://health.kdca.go.kr/healthinfo/biz/health/ntcnInfo/healthSourc/thtimtCntnts/thtimtCntntsView.do?thtimt_cntnts_sn=7>
- NHIS 직역·성별·연령별 건강검진정보: <https://www.data.go.kr/data/15144521/fileData.do>
- NHIS 건강검진청구항목코드: <https://www.data.go.kr/data/15132486/fileData.do>

## 재현 명령

`06_재현성`은 감사용 코드 사본입니다. 스크립트와 테스트를 원래 저장소 구조의 `scripts`, `tests`, `storage/source_document` 위치에 두고 저장소 루트에서 다음 명령으로 검증합니다.

```bash
python3 -m pip install -r requirements-vdb.txt
python3 scripts/preprocess_screening_regulation.py --check
python3 scripts/preprocess_nhis_screening.py --check
python3 -m unittest discover -s tests -v
python3 scripts/manage_vdb.py validate
python3 scripts/evaluate_vdb.py
```

패키지 생성일: 2026-07-16 (Asia/Seoul)  
패키지 버전: `health-screening-share-v1`
