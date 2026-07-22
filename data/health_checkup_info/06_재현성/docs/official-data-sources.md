# 실제 연동 가능한 건강검진 공식 데이터

이 문서는 소개 기사나 보도자료가 아니라, 실제 응답 또는 파일 다운로드를 확인한 주소만 정리합니다.
확인일은 2026-07-16입니다.

CSV 직접 다운로드 주소는 확인 당시 스냅샷입니다. 새 버전이 등록되면 공공데이터포털의 최신
메타데이터와 체크섬을 확인한 뒤 `source_document`에 새 버전으로 보관합니다.

## 1. 바로 호출할 수 있는 JSON API

모든 `api.odcloud.kr` 요청에는 공공데이터포털에서 발급받은 서비스 키가 필요합니다.
아래 URL에는 키를 포함하지 않았습니다.

### 건강검진 결과 집계

- 용도: 연도·직역·성별·연령별 정상A/B, 질환의심, 유질환자 인원 검증
- 한계: 개인별 혈압  ·혈당·콜레스테롤 수치는 없음
- 데이터: 2022~2023년, 180행
- API: <https://api.odcloud.kr/api/15144521/v1/uddi:281e8b27-402b-48db-85d9-d5410a73ce07>
- Swagger JSON: <https://infuser.odcloud.kr/oas/docs?namespace=15144521/v1>
- CSV 직접 다운로드: <https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003189495&fileDetailSn=1&insertDataPrcus=N>

```bash
curl -G 'https://api.odcloud.kr/api/15144521/v1/uddi:281e8b27-402b-48db-85d9-d5410a73ce07' \
  --data-urlencode 'page=1' \
  --data-urlencode 'perPage=100' \
  --data-urlencode "serviceKey=$DATA_GO_KR_SERVICE_KEY"
```

### 건강검진 검사항목 코드

- 용도: 건강검진 항목 코드, 코드명, 검진유형, 상세구분 매핑
- 한계: 정상범위와 판정조건은 포함하지 않음
- API: <https://api.odcloud.kr/api/15132510/v1/uddi:14a6a890-74e1-4c8e-9e24-84961db0ad05>
- Swagger JSON: <https://infuser.odcloud.kr/oas/docs?namespace=15132510/v1>
- CSV 직접 다운로드: <https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003630992&fileDetailSn=1&insertDataPrcus=N>

```bash
curl -G 'https://api.odcloud.kr/api/15132510/v1/uddi:14a6a890-74e1-4c8e-9e24-84961db0ad05' \
  --data-urlencode 'page=1' \
  --data-urlencode 'perPage=2000' \
  --data-urlencode "serviceKey=$DATA_GO_KR_SERVICE_KEY"
```

### 건강검진 검사항목 기본

- 용도: 건강검진 항목 코드, 코드명, 일반·암·구강 등 도메인 매핑
- API: <https://api.odcloud.kr/api/15133104/v1/uddi:071dd3a1-89a1-4a65-b890-f4528e16ae2f>
- Swagger JSON: <https://infuser.odcloud.kr/oas/docs?namespace=15133104/v1>
- CSV 직접 다운로드: <https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003630993&fileDetailSn=1&insertDataPrcus=N>

### 건강검진 청구항목 코드

- 용도: 검진기관 청구 항목 및 검진유형 코드 매핑
- 한계: 실제 검사 결과 항목과 혼동하면 안 됨
- API: <https://api.odcloud.kr/api/15132486/v1/uddi:775e4de2-f15a-4a67-84ef-9a5e50306558>
- Swagger JSON: <https://infuser.odcloud.kr/oas/docs?namespace=15132486/v1>
- CSV 직접 다운로드: <https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003630990&fileDetailSn=1&insertDataPrcus=N>

## 2. 판정규칙을 만들 때 사용하는 원문 파일

아래 문서는 자동 API가 아니라 버전을 관리하며 정규화해야 하는 원문입니다.

### 국가건강검진 판정기준

- 검사항목별 판정기준 원문:
  <https://law.go.kr/LSW/flDownload.do?bylClsCd=200207&flNm=%5B%EB%B3%84%EC%B2%A8+1%5D+%EA%B2%80%EC%82%AC%ED%95%AD%EB%AA%A9%EB%B3%84+%ED%8C%90%EC%A0%95%EA%B8%B0%EC%A4%80&flSeq=160922929>
- 일반건강검진 결과통보서 원문:
  <https://law.go.kr/LSW/flDownload.do?bylClsCd=200203&flNm=%5B%EB%B3%84%EC%A7%80+6%5D+%EC%9D%BC%EB%B0%98%EA%B1%B4%EA%B0%95%EA%B2%80%EC%A7%84+%EA%B2%B0%EA%B3%BC%ED%86%B5%EB%B3%B4%EC%84%9C&flSeq=160922671>
- 저장 대상: `source_document`
- 구조화 대상: `screening_rule`, `screening_item_mapping`
- VDB 대상: 아님
- 현행 기준: 보건복지부고시 제2026-6호, 2026-01-07 시행
- 원문 체크섬: `5f804efa7257c067eabe8084cff6b9fb3d140f8f33e10234fc5423351f6ed11a`

### 질환별 심화 판정 근거

공개된 단일 `수치 -> 질병 -> 추가검사` API는 없습니다. 질환별 진료지침에서 규칙을 직접 구조화하고
의료진 검수를 거쳐야 합니다.

- 2025 당뇨병 진료지침 PDF:
  <https://diabetes.or.kr/bbs/download.php?code=guide&number=1522>
- 대한신장학회 진료지침 목록:
  <https://www.ksn.or.kr/bbs/?code=g_guideline>
- 국가건강정보포털 콘텐츠 API 신청:
  <https://health.kdca.go.kr/healthinfo/biz/health/portalUseGuidance/hlthinsReqst/hlthinsReqstMth.do>

진료지침 전체를 VDB에 복제하지 않습니다. `source_document`에는 원문 위치·버전·체크섬을 기록하고,
`clinical_interpretation_rule`에는 검수된 수치 규칙만 저장합니다. 설명문은 사용허가를 확인한 뒤
`knowledge_chunk`에 적재합니다.

## 3. 직접 연동 데이터가 아닌 자료

다음 자료는 실제 수집 API로 등록하지 않습니다.

| 자료 | 처리 |
|---|---|
| 저위험 표본데이터 보도자료 | 출처에서 제외 |
| 저위험 표본데이터 | 건강보험 빅데이터 플랫폼 신청형 연구자료로 별도 관리 |
| 건강정보 고속도로 소개 페이지 | 공개 API 엔드포인트가 아니므로 출처에서 제외 |
| 과거 건강검진정보 100만 건 데이터 ID `15007122` | 폐기된 데이터이므로 수집기에서 제외 |

## 4. 결론

- 실제 자동 수집: 건보공단의 코드 API와 집계 API
- 실제 판정 기준: 국가법령정보센터 원문을 정규화한 `screening_rule`
- 심화 해석: 학회 진료지침에서 직접 만든 `clinical_interpretation_rule`
- 질환 설명: 허가가 확인된 설명문만 `knowledge_chunk`에 적재
- 공개 개인별 검진 결과 API: 현재 없음

## 5. VDB에 실제 적재한 자료

- 자체 작성 국가건강검진 핵심 설명 30개:
  `vdb/corpus/screening_core_v1.json`
- 각 청크는 현행 고시 또는 정부·전문학회 실제 원문 URL과 문서 위치를 보유
- 수치 판정은 청크에서 제거하고 `database/seeds/020_screening_dictionary.sql`에만 적재
- 질병관리청 국가건강정보포털은 공공누리 제4유형이므로 원문 임베딩하지 않음
- 학회 진료지침은 사용허가 전까지 참고 링크로만 관리
