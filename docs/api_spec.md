# API 명세서

- 작성자: 김진우
- Base URL: `http://localhost:8000`
- 검색 저장소: Pinecone
- 임베딩 모델: `jhgan/ko-sroberta-multitask` 로컬 768차원

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

`/search/combined`와 동일한 병렬 검색·병합 결과에 `C1`, `C2` 순서의 청크 ID를 붙여 Gemini 답변을 생성합니다. 모든 답변은 각 건강정보 주장에 `[C1]` 형식의 인용을 요구하고 서버가 인용 ID를 검사합니다. `comprehensive`, `ignore`, Safety Guard 감지, Intent 저신뢰 또는 분류기 미준비 상황에서는 별도 Gemini 검증 단계가 답변 주장과 인용 청크의 의미 일치 여부까지 확인합니다. 검색 결과가 없거나 필수 검증에 실패하면 답변을 통과시키지 않고 `grounded=false`를 반환합니다.

요청:

```json
{"question":"공복혈당과 복용 약의 관계를 알려줘"}
```

응답에는 기존 `answer`, `sources`, `grounded`와 함께 답변 생성 문맥에 전달한 최종 실제 청크 `chunks`, 검증을 통과한 실제 인용 `citations`, 검증 실패 원인, namespace 처리 상태가 포함됩니다. `chunks[].text`와 `citations[].text`는 미리보기가 아닌 전체 청크 본문입니다.

```json
{
  "answer": "공복혈당은 일정 시간 금식한 뒤 측정합니다. [C1]\n\n이 답변은 의료 진단이 아닌 정보 제공 목적입니다.",
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
  "verification_method": "citation_only",
  "verification_reason": "intent:simple_lookup",
  "grounding_errors": [],
  "unsupported_claims": [],
  "searched_collections": ["health_checkup_info", "disease_info"],
  "failed_collections": []
}
```

`chunks`는 Gemini에 제공한 전체 최종 문맥이고, `citations`는 답변 본문이 실제로 인용했으며 해당 요청의 필수 검증을 통과한 청크다. `grounded=true`는 다음 조건을 모두 만족할 때만 반환한다.

- 답변 본문에 하나 이상의 유효한 `[C숫자]` 인용이 있음
- 본문 인용과 구조화 출력의 인용 목록이 일치함
- 존재하지 않는 청크 ID가 없음
- 강화 검증 대상이면 별도 검증 결과 모든 건강정보 주장이 인용 청크로 뒷받침됨

조건부 검증 정책은 다음과 같다.

| 조건 | `verification_method` | Gemini 호출 |
|---|---|---:|
| `simple_lookup`, `general_chat` | `citation_only` | 1회 |
| `comprehensive`, `ignore` | `llm_verified` | 2회 |
| Safety Guard 감지 | `llm_verified` | 2회 |
| Intent `uncertain=true` | `llm_verified` | 2회 |
| Intent 분류기 미준비 | `llm_verified` | 2회 |
| 인용 형식 또는 근거 검증 실패 | `citation_validation_failed` 또는 `llm_verification_failed` | 단계에 따라 1~2회 |

`verification_reason`은 `intent:simple_lookup`, `intent:comprehensive`, `safety_guard:medication_decision`, `intent_uncertain`, `intent_classifier_unavailable`처럼 정책 선택 근거를 반환한다.

다중 검색 기본 설정은 구조 검증용이며 전체 데이터 적재 후 평가를 통해 조정합니다.

```text
SEARCH_COLLECTIONS=health_checkup_info,disease_info
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
| `500` | Pinecone, 임베딩 모델 또는 Gemini 호출 오류 |

## collection과 namespace

서버 시작 시 `vdb/chunk/[collection_name]` 하위 폴더를 collection으로 자동 등록하며 같은 이름을 Pinecone namespace로 사용합니다. 새 collection 폴더를 추가한 뒤에는 서버를 재시작합니다.

현재 collection 예시는 다음과 같습니다.

| API collection | Pinecone namespace |
|---|---|
| `disease_info` | `disease_info` |
| `health_checkup_info` | `health_checkup_info` |
