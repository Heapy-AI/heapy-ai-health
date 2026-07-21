# VDB 출처 조사·사용성 감사

확인일: 2026-07-16

## 1. 운영 결정

| 출처 | 실제 자료 | 역할 | VDB 적재 결정 |
|---|---|---|---|
| 보건복지부 | [2026 건강검진 실시기준](https://law.go.kr/LSW/admRulLsInfoP.do?admRulId=38208&efYd=0) 및 검사항목별 판정기준 PDF | 항목·판정 수치 | VDB 금지, RDB 규칙으로 구조화 |
| 식품의약품안전처 | [e약은요 OpenAPI](https://www.data.go.kr/data/15075057/openapi.do) | 효능·사용법·주의·상호작용·부작용 | 이용범위 제한 없음. 사용자 복약 품목만 동적 청크 생성 |
| 질병관리청 | [국가건강정보포털 OpenAPI](https://www.data.go.kr/data/15087442/openapi.do) | 환자용 건강 설명 | 공공누리 제4유형·변경금지. 허가 전 원문 임베딩 금지 |
| 대한당뇨병학회 | [2025 당뇨병 진료지침 PDF](https://diabetes.or.kr/bbs/download.php?code=guide&number=1522) | 혈당 근거 검토 | 참고만, 원문 임베딩 금지 |
| 대한신장학회 | [당뇨병콩팥병 진료지침 PDF](https://www.ksn.or.kr/bbs/skin/publication/download.php?code=g_guideline&number=2159) | eGFR·알부민뇨 근거 검토 | 참고만, 원문 임베딩 금지 |
| 한국지질·동맥경화학회 | [이상지질혈증 진료지침](https://www.lipid.or.kr/reference/guideline.php) | 지질검사 근거 검토 | 참고만, 원문 임베딩 금지 |
| 대한간학회 | [2026 만성 B형간염 진료 가이드라인](https://www.kasl.org/bbs/skin/guide/pdf_inline.php?code=guide&number=17947) | AST·ALT·GGT 근거 검토 | 참고만, 원문 임베딩 금지 |
| 자체 설명 가이드 | `vdb/corpus/screening_core_v1.json` | MVP 단순조회 답변 | 자체 작성 30청크. 출처검증 완료, 임상검수 대기 |

## 2. 제외한 자료

- 일반 기사·블로그·검색 결과 요약: 원문 근거가 아니므로 제외
- AI Hub 의료 질의응답: 검진 20~30개 단순 설명 범위를 벗어나고 개별 응답의 근거 추적이 어려워 MVP에서 제외
- HIRA 질병코드 조회 API: 질병명·코드 매핑 자료이지 검진수치 설명문이 아니므로 VDB에서 제외
- 건강보험 저위험 표본데이터: 연구·통계 검증용이며 사용자 질문의 설명 근거가 아니므로 VDB에서 제외
- 사용자가 올린 검진결과·처방전: 개인정보이므로 VDB에 임베딩하지 않고 RDB에만 저장

## 3. 출처 충돌 발견

질병관리청의 기존 [건강검진 결과 해석 페이지](https://health.kdca.go.kr/healthinfo/biz/health/ntcnInfo/healthSourc/thtimtCntnts/thtimtCntntsView.do?thtimt_cntnts_sn=7)는
HDL 설명 하단의 정상·낮음 수치 방향이 현행 보건복지부 판정기준과 반대로 표시된 부분이 있습니다.

처리 원칙은 다음과 같습니다.

- 모든 숫자 판정은 2026년 보건복지부 고시만 사용
- 질병관리청 페이지는 용어 설명 참고로만 사용
- VDB 청크에는 숫자 판정값을 넣지 않음
- 답변 시 RDB 판정과 VDB 설명을 조합

## 4. 라이선스 게이트

- `source_registry.license_status = APPROVED`이고 `is_active = TRUE`인 출처만 검색할 수 있습니다.
- 법령·고시는 저작권법 제7조의 보호받지 못하는 저작물 범주를 근거로 수치 규칙을 구조화했습니다.
- 질병관리청 제4유형 콘텐츠와 학회 지침은 원문을 복제하지 않고 근거 확인용 링크만 보존했습니다.
- 자체 설명문은 전문학회·정부 자료의 문장을 복사하지 않고 검진항목의 의미와 해석 한계를 새로 작성했습니다.

