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

질문을 로컬 모델로 한 번 임베딩한 뒤 Linear/Softmax 분류기로 최상위 intent를 반환합니다.

요청:

```json
{"question":"최근 AST가 높은데 왜 그런가요?"}
```

응답에는 `intent`, `confidence`, intent별 `probabilities`, `uncertain`, `model_version`이 포함됩니다. 학습된 모델 artifact가 없으면 `503`을 반환합니다.

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

## 오류

| 상태 | 조건 |
|---|---|
| `400` | 등록되지 않은 collection |
| `422` | 요청 필드 누락 또는 형식 오류 |
| `503` | 학습된 intent 모델 artifact 없음 |
| `500` | Pinecone, 임베딩 모델 또는 Gemini 호출 오류 |

## collection과 namespace

서버 시작 시 `vdb/chunk/[collection_name]` 하위 폴더를 collection으로 자동 등록하며 같은 이름을 Pinecone namespace로 사용합니다. 새 collection 폴더를 추가한 뒤에는 서버를 재시작합니다.

현재 collection 예시는 다음과 같습니다.

| API collection | Pinecone namespace |
|---|---|
| `disease_info` | `disease_info` |
| `health_checkup_info` | `health_checkup_info` |
