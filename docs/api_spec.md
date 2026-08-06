# API 명세서

- 작성자: 김진우
- Base URL: `http://localhost:8000`
- 검색 저장소: Pinecone
- 임베딩 모델: `jhgan/ko-sroberta-multitask` 로컬 768차원

## `GET /`

HEAPY 챗봇 MVP 시연용 웹 앱을 반환합니다. 웹 앱은 별도 프론트엔드 서버 없이
FastAPI와 함께 실행되며 `POST /chat/stream`을 호출합니다. 현재 적재·검토가 끝나지 않은
복약정보는 화면에서 `검토 중`으로 표시하며, 실제 API 응답에 포함된 Intent·근거
검증·출처만 답변 정보 패널에 노출합니다.

## `GET /health`

Pinecone 연결과 namespace별 적재 수를 반환합니다.

```json
{
  "status": "ok",
  "ready": true,
  "vector_backend": "pinecone",
  "indexed_chunks": {
    "disease_info": 54330,
    "health_checkup_info": 30
  },
  "embed_model": "jhgan/ko-sroberta-multitask",
  "intent_classifier": {
    "ready": false,
    "model_version": null
  }
}
```

등록된 namespace 중 하나라도 0건이면 `ready=false`입니다.

## `POST /chat`

MVP 통합 챗봇 엔드포인트입니다. Safety Guard를 먼저 실행하고, 통과한 질문은 동일한 질문 임베딩으로 Intent v6를 분류합니다. 분류 결과에 따라 다음 경로를 실행합니다.

| Intent | 처리 경로 |
|---|---|
| `simple_lookup` | Pinecone 병렬 검색 → 근거 계획 선검증 → 최종 답변 생성 → 사후 감사 |
| `comprehensive` | Pinecone 병렬 검색 → 강화 근거 계획 선검증 → 최종 답변 생성 → 사후 감사 |
| `general_chat` | Pinecone 검색 없이 Gemini 일반 대화 |
| `ignore` | Pinecone 및 Gemini 호출 없이 고정 답변 |

Safety Guard가 작동하면 Intent 모델과 임베딩을 실행하지 않고 바로 `ignore` 고정 응답을 반환합니다. `simple_lookup`과 `comprehensive`는 Intent 분류에 사용한 질문 임베딩을 Pinecone 검색에 재사용합니다.

요청:

```json
{"question":"건강검진에서 AST가 높게 나왔는데 왜 그런가요?"}
```

응답에는 Intent 분류 정보, 답변, 실제 검색 청크, 검증된 인용 및 namespace 처리 상태가 함께 포함됩니다. `grounded`는 RAG 경로에서만 `true` 또는 `false`이며 검색하지 않는 `general_chat`과 `ignore`는 `null`입니다. 현재 MVP는 개인 건강·복약 RDB가 연결되지 않았으므로 `comprehensive`도 `personal_context_used=false`입니다.

## `POST /chat/stream`

`POST /chat`과 동일한 질문 분류·검색·검증 흐름을 실행하면서 응답을
`text/event-stream` 형식으로 반환합니다. 요청 JSON은 동일합니다.

```json
{"question":"공복혈당 정상 수치는 어떻게 되나요?"}
```

이벤트는 다음 순서로 전달됩니다.

| 이벤트 | 데이터 | 설명 |
|---|---|---|
| `token` | `{"text":"생성된 문자열"}` | Gemini가 생성한 답변 조각 |
| `complete` | `ChatResponse` 전체 JSON | 스트리밍 본문과 근거 계획·사후 감사 메타데이터 |
| `error` | `{"message":"안내 문구"}` | 스트림 시작 이후 발생한 처리 오류 |

```text
event: token
data: {"text":"공복혈당은 "}

event: token
data: {"text":"금식 후 측정합니다."}

event: complete
data: {"question":"...","answer":"...","grounded":true,...}
```

RAG 경로는 검색 청크에서 `grounding_plan`을 먼저 생성하고 청크 ID와 답변 가능성을
검사합니다. 계획이 승인된 경우에만 최종 사용자 답변을 스트리밍합니다. 스트리밍이
끝나면 승인된 계획과 실제 답변을 다시 대조한 사후 감사를 수행하며, 결과는
`audit_status`, `audit_summary`, `unsupported_claims`에 기록합니다.

사후 감사 결과는 이미 표시한 답변 본문을 교체하지 않습니다. 정상 완료 시
`complete.answer`는 모든 `token.text`를 순서대로 연결한 문자열과 동일해야 합니다.
근거 연결은 본문 인용 라벨 대신 `grounding_plan`, `citations`, `chunks`에서 확인합니다.

`general_chat`은 Gemini 토큰을 스트리밍합니다. `ignore`와 Safety Guard 응답은
LLM을 호출하지 않으며 고정 문구를 하나의 `token` 이벤트로 전달한 뒤 즉시
`complete` 이벤트를 전송합니다. 기존 `POST /chat`은 비스트리밍 클라이언트와의
호환을 위해 유지합니다.

웹 앱은 서버의 SSE 수신 속도와 화면 표시 속도를 분리합니다. 수신한 문자열을
기본 28ms/글자 간격으로 표시하고 쉼표와 문장 끝에서 각각 조금 더 기다립니다.
표시 대기 문자열이 길면 한 번에 두 글자씩 처리하며, `complete`를 먼저 받더라도
표시 대기열을 모두 비운 뒤 사후 감사 카드를 추가합니다. 이 지연은
화면의 가독성을 위한 것으로 서버 LLM 호출이나 근거 검증 시간을 늘리지 않습니다.

## `POST /intent/classify`

질문을 먼저 규칙 기반 Safety Guard로 확인하고, 통과한 질문만 로컬 모델로 한 번 임베딩한 뒤 Linear/Softmax 분류기로 최상위 intent를 반환합니다.

현재 기본 체크포인트는 `classifier/artifacts/intent-v6/best_model.json`이며, 환경변수 `INTENT_MODEL_PATH`로 다른 버전을 선택할 수 있습니다.

요청:

```json
{"question":"최근 AST가 높은데 왜 그런가요?"}
```

기존 필드인 `intent`, `confidence`, intent별 `probabilities`, `uncertain`, `model_version`은 유지합니다. 분류 출처 확인을 위해 `source`, `guard_triggered`, `guard_reason`, `matched_patterns`를 추가로 반환합니다.

Safety Guard가 작동하면 `intent=ignore`, `source=safety_guard`, `confidence=1.0`, `uncertain=false`를 반환합니다. 규칙이 명시적인 의료적 결정 요청을 확정적으로 라우팅하므로 1.0을 사용하며, 일반적인 모델 confidence와는 의미가 다릅니다. Guard를 통과하면 `source=linear_classifier`입니다.

## `POST /search`

LLM 호출 없이 질문과 유사한 Pinecone 청크를 반환합니다.

요청:

```json
{
  "question": "공복혈당이 무엇인가요?",
  "collection": "health_checkup_info"
}
```

응답:

```json
{
  "query": "공복혈당이 무엇인가요?",
  "hits": [
    {
      "source": "건강검진 검사항목별 판정기준 · https://...",
      "text": "공복혈당은 일정 시간 금식한 뒤..."
    }
  ]
}
```

## `POST /ask`

Pinecone 검색 청크를 근거로 Gemini 답변을 생성합니다.

요청:

```json
{
  "question": "건강검진 정상B는 무슨 뜻이야?",
  "collection": "health_checkup_info"
}
```

응답:

```json
{
  "answer": "정상B는 생활습관 관리나 예방조치가 필요한 상태를 뜻합니다...",
  "sources": ["보건복지부 건강검진 실시기준 · https://..."],
  "grounded": true
}
```

검색 청크에 근거가 없으면 `지식베이스에 근거 없음`, `grounded=false`를 반환합니다.

## `POST /search/combined`

질문을 한 번 임베딩하고 `SEARCH_COLLECTIONS`에 설정된 Pinecone namespace를 병렬 검색합니다. 결과를 중복 제거·점수 정렬·컬렉션 편중 제한 후 반환하며 Gemini는 호출하지 않습니다.

요청:

```json
{"question":"공복혈당과 복용 약의 관계를 알려줘"}
```

응답:

```json
{
  "query": "공복혈당과 복용 약의 관계를 알려줘",
  "hits": [
    {
      "collection": "health_checkup_info",
      "score": 0.93,
      "source": "건강검진 판정기준 · https://...",
      "text": "공복혈당은 일정 시간 금식한 뒤..."
    }
  ],
  "searched_collections": ["health_checkup_info", "disease_info"],
  "failed_collections": []
}
```

## `POST /ask/combined`

`/search/combined`와 동일한 병렬 검색·병합 결과에 `C1`, `C2` 순서의 청크 ID를 붙이고,
답변에 사용할 사실과 근거 ID를 `grounding_plan`으로 먼저 확정합니다. 계획이 승인되면
해당 사실만 사용해 최종 답변을 생성하고, 생성 후 계획 이탈 여부를 사후 감사합니다.
검색 결과가 없거나 계획 선검증에 실패하면 답변 생성을 시작하지 않고
`지식베이스에 근거 없음`을 반환합니다.

요청:

```json
{"question":"공복혈당과 복용 약의 관계를 알려줘"}
```

응답에는 기존 `answer`, `sources`, `grounded`와 함께 답변 생성 문맥에 전달한 최종 실제 청크 `chunks`, 검증을 통과한 실제 인용 `citations`, 검증 실패 원인, namespace 처리 상태가 포함됩니다. `chunks[].text`와 `citations[].text`는 미리보기가 아닌 전체 청크 본문입니다.

```json
{
  "answer": "공복혈당은 일정 시간 금식한 뒤 측정합니다.",
  "sources": ["건강검진 판정기준 · https://..."],
  "grounded": true,
  "chunks": [
    {
      "collection": "health_checkup_info",
      "record_id": "FASTING_GLUCOSE",
      "score": 0.93,
      "source": "건강검진 판정기준 · https://...",
      "text": "공복혈당은 일정 시간 금식한 뒤 혈액 속 포도당 농도를..."
    }
  ],
  "citations": [
    {
      "citation_id": "C1",
      "collection": "health_checkup_info",
      "record_id": "FASTING_GLUCOSE",
      "score": 0.93,
      "source": "건강검진 판정기준 · https://...",
      "text": "공복혈당은 일정 시간 금식한 뒤 혈액 속 포도당 농도를..."
    }
  ],
  "verification_method": "prevalidated_post_audit",
  "verification_reason": "intent:simple_lookup",
  "grounding_plan": {
    "answerable": true,
    "facts": [
      {"statement": "공복혈당은 일정 시간 금식한 뒤 측정합니다.", "cited_chunk_ids": ["C1"]}
    ],
    "reason": "검색 청크가 질문에 직접 답합니다."
  },
  "audit_status": "passed",
  "audit_summary": "최종 답변이 승인된 근거 계획을 준수했습니다.",
  "grounding_errors": [],
  "unsupported_claims": [],
  "searched_collections": ["health_checkup_info", "disease_info"],
  "failed_collections": []
}
```

`chunks`는 근거 계획에 제공한 전체 최종 문맥이고, `citations`는 승인된 계획의 사실과
연결된 청크다. 사용자 표시용 `answer`에는 인용 라벨이 포함되지 않는다.
`grounded=true`는 근거 계획이 답변 가능 상태이고 모든 사실에 유효한 청크 ID가
연결된 경우 반환한다. 사후 감사 실패는 `audit_status=failed`로 기록하지만 이미
스트리밍된 본문을 다른 문장으로 교체하지 않는다.

검증·감사 정책은 다음과 같다.

| 조건 | 처리 |
|---|---|
| `simple_lookup` | 기본 근거 계획 선검증 → 최종 답변 → 사후 감사 |
| `comprehensive`, Intent 저신뢰 | 강화 근거 계획 선검증 → 최종 답변 → 사후 감사 |
| 계획 거절 | 최종 생성 없이 근거 없음 고정 응답 |
| `general_chat` | Safety Guard 통과 후 일반 대화 스트리밍, 감사 비대상 |
| `ignore`, Safety Guard | LLM 없이 고정 응답, 감사 비대상 |

`verification_reason`은 `intent:simple_lookup`, `intent:comprehensive`, `safety_guard:medication_decision`, `intent_uncertain`, `intent_classifier_unavailable`처럼 정책 선택 근거를 반환한다.

다중 검색 기본 설정은 구조 검증용이며 전체 데이터 적재 후 평가를 통해 조정합니다.

```text
SEARCH_COLLECTIONS=health_checkup_info,disease_info,medication_info
SEARCH_TOP_K_PER_COLLECTION=3
SEARCH_FINAL_TOP_K=6
SEARCH_MAX_PER_COLLECTION=2
SEARCH_MIN_SCORE=0.0
```

## 오류

| 상태 | 조건 |
|---|---|
| `400` | 등록되지 않은 collection |
| `422` | 요청 필드 누락 또는 형식 오류 |
| `503` | 학습된 intent 모델 artifact 없음 |
| `503` | 다중 검색 대상 namespace가 모두 실패 |
| `503` | 통합 챗봇 오케스트레이터가 준비되지 않음 |
| `500` | Pinecone, 임베딩 모델 또는 Gemini 호출 오류 |

## collection과 namespace

서버 시작 시 `vdb/chunk/[collection_name]` 하위 폴더를 collection으로 자동 등록하며 같은 이름을 Pinecone namespace로 사용합니다. 새 collection 폴더를 추가한 뒤에는 서버를 재시작합니다.

현재 collection 예시는 다음과 같습니다.

| API collection | Pinecone namespace |
|---|---|
| `disease_info` | `disease_info` |
| `health_checkup_info` | `health_checkup_info` |
| `medication_info` | `medication_info` |
