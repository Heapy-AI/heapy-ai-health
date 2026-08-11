# HEAPY API 명세서

- 작성자: 김진우
- Base URL: `http://localhost:8000`
- 검색 저장소: Pinecone
- 임베딩 모델: `jhgan/ko-sroberta-multitask` 768차원
- 기본 Intent 체크포인트: `classifier/artifacts/intent-v7/best_model.json`

## 공통 처리 흐름

```text
사용자 질문
→ 대화 이력·요약을 사용한 후속 질문 독립형 재작성
→ RDB 의료용어 정규화 및 필요 시 사용자 확인
→ 정규화 질문 임베딩 및 Intent v7 분류
→ 원문·정규화 질문의 Safety Guard 정책 병합
→ Intent별 처리
  ├─ simple_lookup / comprehensive: Pinecone 병렬 검색
  ├─ general_chat: 검색 없는 일반 대화
  └─ ignore: 건강 서비스 외 고정 응답
→ 검색 결과 기본 검사
→ 근거가 있는 항목만 최종 답변 생성·스트리밍
→ 사후 감사 및 개발자 모니터링 기록
```

Safety Guard는 Intent를 변경하지 않는다. 다음 정보만 생성해 최종 답변 프롬프트의
허용 범위를 제한한다.

- `risk_level`: `normal`, `caution`, `emergency`. 위험 단어 하나가 아니라 위험 증상,
  개인·현재 상황, 즉시 행동 요청, 일반 정보형 의문문을 함께 판정한다.
- `restricted_actions`: 확정 진단, 개인 처방, 복용량 변경, 복약 중단, 내원 여부 결정
- `response_policy`: 일반 근거 답변, 제한된 안전 안내, 긴급 안내 우선
- `emergency`: 긴급 안내 우선 여부

## `GET /`

FastAPI와 함께 실행되는 개발·검증용 웹 앱을 반환한다. 중앙에는 챗봇, 왼쪽에는
프로젝트 환경, 오른쪽에는 질문별 검색 결과 검사·안전 정책·사후 감사·원본 JSON을
표시한다.

## `GET /health`

Pinecone 연결, namespace별 적재 수, 임베딩 모델, Intent 모델 준비 상태를 반환한다.

```json
{
  "status": "ok",
  "ready": true,
  "vector_backend": "pinecone",
  "indexed_chunks": {
    "disease_info": 54330,
    "health_checkup_info": 30,
    "medication_info": 43330
  },
  "embed_model": "jhgan/ko-sroberta-multitask",
  "intent_classifier": {
    "ready": true,
    "model_version": "intent-v7-41c86ac21d53"
  }
}
```

## `POST /intent/classify`

Intent 분류와 독립적인 Safety Guard 정책을 함께 반환한다. Guard가 작동해도
`source=linear_classifier`이며 Intent와 confidence를 덮어쓰지 않는다.

요청:

```json
{"question":"감기 걸린 것 같은데 어떻게 할까?"}
```

응답 예시:

```json
{
  "intent": "comprehensive",
  "confidence": 0.91,
  "probabilities": {
    "simple_lookup": 0.04,
    "comprehensive": 0.91,
    "general_chat": 0.03,
    "ignore": 0.02
  },
  "uncertain": false,
  "model_version": "intent-v7-41c86ac21d53",
  "source": "linear_classifier",
  "guard_triggered": true,
  "guard_reason": "personal_symptom_guidance",
  "matched_patterns": ["감기 걸린 것 같은데 어떻게"],
  "risk_level": "caution",
  "restricted_actions": ["definitive_diagnosis"],
  "response_policy": "grounded_safe_guidance",
  "emergency": false
}
```

## `POST /chat`

Intent 분류부터 검색·생성·감사까지 실행한 전체 결과를 JSON으로 반환한다.

멀티턴 요청은 최근 대화와 이전 응답의 요약을 함께 전달한다. 의료용어 확인 응답을
이어갈 때는 서버가 반환한 `confirmation_id`와 사용자의 `confirmation_answer`를
전달한다.

```json
{
  "question": "그 약 부작용은?",
  "history": [
    {"role": "user", "content": "부루펜을 먹었어"},
    {"role": "assistant", "content": "어떤 정보가 궁금하신가요?"}
  ],
  "summary": "",
  "confirmation_id": "",
  "confirmation_answer": null
}
```

질문 처리 단계는 `original_question`(원문), `standalone_question`(대화 문맥 복원),
`resolved_query`(의료용어 정규화 및 실제 임베딩·검색 질문)로 구분한다. 응답에는
`query_rewritten`, `resolved_terms`, `resolution_status`, `conversation_summary`도
포함된다. `resolution_status=CONFIRM` 또는 `AMBIGUOUS`이면 임베딩과 검색을 보류한다.

후속 질문 재작성은 첫 질문에서는 실행하지 않는다. 이전 대화가 있으면 문맥 지시어,
`낮추려면`, `부작용은` 같은 대상 생략 표현을 우선 탐지하고, 명시적 주제가 확인되지
않는 애매한 질문도 재작성 모델이 최종 판단하도록 전달한다. 질문 길이는 재작성 여부의
판정 기준으로 사용하지 않는다.

| Intent | 처리 경로 |
|---|---|
| `simple_lookup` | 일반 질병·검사·의약품 정보용 Pinecone RAG |
| `comprehensive` | 개인 증상·상황·개인 데이터가 필요한 Pinecone RAG. 현재 개인 RDB는 미연결 |
| `general_chat` | Pinecone 검색 없이 Gemini 일반 대화 |
| `ignore` | 주식·날씨·스포츠·코딩 등 건강 서비스 외 고정 답변 |

RAG의 기본 검색 결과 검사는 다음을 구분한다.

| `retrieval_assessment.status` | 의미 |
|---|---|
| `no_evidence` | 최소 유사도 기준을 통과한 청크가 없음 |
| `entity_mismatch` | 질문의 명시 의약품·질병명과 청크 대상이 일치하지 않음 |
| `evidence_available` | 생성 가능한 청크와 대상 일치를 확인함 |

사후 감사의 `evidence_status`는 `sufficient`, `partial`, `insufficient`, `unknown` 중
하나이다. 복합 질문에서 일부 항목만 근거가 있으면 `partial`로 기록하고, 근거가 있는
항목은 답하면서 `unanswered_items`에 근거 부족 항목을 남긴다.

응답 예시:

```json
{
  "question": "판콜에스내복액이 무슨 약이고 부작용은 뭐야?",
  "intent": "simple_lookup",
  "confidence": 0.93,
  "probabilities": {},
  "uncertain": false,
  "model_version": "intent-v7-41c86ac21d53",
  "intent_source": "linear_classifier",
  "guard_triggered": false,
  "guard_reason": null,
  "matched_patterns": [],
  "risk_level": "normal",
  "restricted_actions": [],
  "response_policy": "standard_grounded",
  "emergency": false,
  "answer": "판콜에스내복액의 효능은 ... 현재 검색 자료에서는 부작용 항목이 확인되지 않았습니다.",
  "sources": ["식품의약품안전처 의약품개요정보(e약은요) OpenAPI"],
  "grounded": true,
  "chunks": [],
  "citations": [],
  "verification_method": "retrieval_check_post_audit",
  "verification_reason": "intent:simple_lookup",
  "grounding_errors": [],
  "unsupported_claims": [],
  "evidence_status": "partial",
  "retrieval_assessment": {
    "status": "evidence_available",
    "eligible": true,
    "reason": "최소 검색 기준을 통과한 청크가 있으며 명시 대상 불일치가 없습니다.",
    "max_score": 0.91,
    "query_entities": ["판콜에스내복액"],
    "matched_entities": ["판콜에스내복액"]
  },
  "audit_status": "passed",
  "audit_summary": "효능은 근거가 있고 부작용은 근거 부족으로 구분했습니다.",
  "unanswered_items": ["부작용"],
  "safety_violations": [],
  "searched_collections": ["disease_info", "health_checkup_info", "medication_info"],
  "failed_collections": [],
  "personal_context_used": false
}
```

## `POST /chat/stream`

`POST /chat`과 같은 흐름을 `text/event-stream`으로 제공한다.

`emergency`는 스트리밍과 RAG를 중단하는 값이 아니다. 긴급 행동 안내를 답변 앞에
배치하고, 검색 청크에서 확인되는 사용자의 요청 정보도 이어서 제공한다.

| 이벤트 | 데이터 | 설명 |
|---|---|---|
| `token` | `{"text":"생성 문자열"}` | 최종 답변 조각 |
| `complete` | `ChatResponse` | 답변과 검색·안전·감사 메타데이터 |
| `error` | `{"message":"안내 문구"}` | 스트리밍 중 오류 |

내부 근거 연결용 `[C1]` 라벨은 서버 스트림 필터가 사용자 답변에서 제거한다. 원본
응답과 감사 기록은 라벨을 이용해 실제 `citations`를 청크에 연결한다. 사후 감사는 이미
표시한 답변을 교체하지 않는다.

## 검색·답변 점검 API

- `POST /search`: 지정 namespace 검색만 수행한다.
- `POST /ask`: 지정 namespace를 사용한 기존 단일 RAG API다.
- `POST /search/combined`: 설정된 모든 namespace를 병렬 검색하고 병합한다.
- `POST /ask/combined`: 병합 청크를 기본 검사한 뒤 생성·감사를 수행한다.

다중 검색 기본 설정:

```text
SEARCH_COLLECTIONS=health_checkup_info,disease_info,medication_info
SEARCH_TOP_K_PER_COLLECTION=10
SEARCH_FINAL_TOP_K=6
SEARCH_MAX_PER_COLLECTION=6
SEARCH_MIN_SCORE=0.0
```

현재 애플리케이션은 namespace별 후보 10개를 모아 전체 정렬한 뒤 최종 6개를 선택한다.

## 오류

| 상태 | 조건 |
|---|---|
| `400` | 등록되지 않은 collection |
| `422` | 요청 필드 누락 또는 형식 오류 |
| `503` | Intent 모델 artifact 없음 또는 모든 namespace 검색 실패 |
| `500` | Pinecone, 임베딩 모델 또는 Gemini 호출 오류 |

## collection과 namespace

| API collection | Pinecone namespace |
|---|---|
| `disease_info` | `disease_info` |
| `health_checkup_info` | `health_checkup_info` |
| `medication_info` | `medication_info` |
