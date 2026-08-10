# HEAPY Intent v7 라벨링 가이드

- 작성자: 김진우
- 적용 모델: Intent v7
- 문서 파일명은 기존 링크 호환을 위해 `v2`를 유지한다.

## 변경 목적

Intent는 질문의 처리 목적만 분류한다. 의료적 위험성과 검색 근거 충족도는 각각
Safety Guard와 RAG 검색 검사에서 판단하며 Intent 라벨로 대신 표현하지 않는다.

특히 `ignore`는 위험한 의료 질문을 차단하는 라벨이 아니라 건강 서비스와 완전히
무관한 질문을 분리하는 라벨로 축소한다.

## Intent 정의

| Intent | 질문 목적 | 현재 처리 |
|---|---|---|
| `simple_lookup` | 일반 질병·검사·의약품 정보 조회 | Pinecone 병렬 검색 기반 RAG |
| `comprehensive` | 사용자의 증상·상황·개인 데이터가 필요한 질문 | Pinecone RAG, 향후 개인 RDB 결합 |
| `general_chat` | 인사·감사·가벼운 대화 | 검색 없는 일반 대화 |
| `ignore` | 주식·날씨·스포츠·코딩 등 건강 서비스 외 질문 | 고정 범위 안내 |

## 핵심 판정 순서

```text
건강 서비스와 완전히 무관한가?
├─ 예 → ignore
└─ 아니오
   ├─ 개인 증상·상황·기록이 필요한가? → comprehensive
   ├─ 일반 건강정보만 필요한가? → simple_lookup
   └─ 인사·감사·가벼운 대화인가? → general_chat
```

진단·처방·복용량 변경·약물 중단·내원 여부 결정을 요구한다는 이유만으로
`ignore`를 부여하지 않는다. 질문 목적에 따라 대부분 `comprehensive`로 분류하고,
Safety Guard가 금지 행동과 위험 수준을 별도로 기록한다.

## 이전 라벨에서 변경되는 대표 예시

| 질문 | v6 | v7 | 이유 |
|---|---|---|---|
| 내가 당뇨병인지 확정해줘 | `ignore` | `comprehensive` | 개인 증상·수치 맥락이 필요한 의료 질문 |
| 이 약을 두 배로 먹어도 돼? | `ignore` | `comprehensive` | 개인 복약 결정 질문이며 Safety 정책으로 제한 |
| 감기 걸린 것 같은데 어떻게 할까? | `ignore` 가능 | `comprehensive` | 확정 진단 없이 일반 정보와 위험 신호 제공 가능 |
| 응급실에 가야 하는지 결정해줘 | `ignore` | `comprehensive` | 긴급 안내를 우선하되 질문 자체는 건강 서비스 범위 |
| 판콜에스내복액의 부작용은? | `simple_lookup` | `simple_lookup` | 일반 의약품 정보 조회 |
| 오늘 환율 알려줘 | `ignore` | `ignore` | 건강 서비스 외 질문 |

## Safety Guard와의 관계

Safety Guard는 다음 메타데이터만 생성한다.

- `risk_level`: `normal`, `caution`, `emergency`
- `restricted_actions`: 확정 진단, 개인 처방, 복용량 변경, 복약 중단, 내원 판단, 개인별 완치·회복 시점 단정
- `response_policy`: 일반 근거 답변, 제한된 안전 안내, 긴급 안내 우선

응급 판정은 `호흡곤란`, `발작` 같은 단어만으로 결정하지 않는다. 위험 증상 표현,
본인에게 현재 발생 중이라는 문맥, 즉시 행동 요청, `증상은?`, `예방하려면?` 같은
일반 정보형 의문문을 함께 본다. 응급으로 판정해도 Intent와 RAG 검색은 유지하고,
긴급 행동 안내 뒤에 검색 근거로 확인되는 요청 정보를 계속 제공한다.

Guard가 작동해도 Intent 모델의 결과와 confidence는 유지한다. 따라서 학습 데이터에
안전 위험을 `ignore`로 표현하지 않는다.

## 데이터 분리 및 검증

- 학습·검증·테스트: 라벨별 80:10:10 고정 seed 분할
- Blind: 라벨별 12건, 총 48건
- 정확히 같은 문장과 공백 정규화 문장의 split 간 중복 금지
- Blind 데이터는 학습·모델 선택에 사용하지 않음
- 의료 결정 질문이 `ignore`로 예측되는 비율과 서비스 외 질문의 Recall을 함께 확인

현재 v7 데이터 생성 결과:

| Split | 전체 | simple | comprehensive | general_chat | ignore |
|---|---:|---:|---:|---:|---:|
| Train | 661 | 159 | 323 | 100 | 79 |
| Validation | 82 | 20 | 40 | 12 | 10 |
| Test | 82 | 20 | 40 | 12 | 10 |
| Blind | 48 | 12 | 12 | 12 | 12 |

Intent v7 체크포인트의 Test Macro F1은 `0.9446`, Blind Macro F1은 `0.9154`다.
Safety Guard는 `metadata_only`로 평가하며 Intent 예측을 덮어쓰지 않는다.
