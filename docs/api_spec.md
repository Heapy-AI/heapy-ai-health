# API 명세서

> **건강정보 봇 RAG 서버** — 검색(Embedding) + 답변(LLM) 분리 설계  
> Base URL: `http://localhost:8000`

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 | LLM 호출 |
|--------|------|------|-----------|
| `GET` | `/health` | 서버·인덱스 상태 점검 | ✗ |
| `POST` | `/search` | 유사 청크 검색 (디버깅용) | ✗ |
| `POST` | `/ask` | 문서 기반 답변 + 출처 반환 | ✓ |

---

## `GET /health`

서버와 인덱스가 정상인지 확인합니다. 모니터링·배포 점검 용도이며 LLM을 호출하지 않습니다.

### 요청

없음

### 응답 `200 OK`

```json
{
  "status": "ok",
  "ready": true,
  "indexed_chunks": 11,
  "embed_model": "jhgan/ko-sroberta-multitask"
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | `string` | 서버 상태. 정상이면 `"ok"` |
| `ready` | `bool` | 인덱스가 준비되어 답변 가능하면 `true` |
| `indexed_chunks` | `int` | 인덱싱된 청크 수. `0`이면 비어 있음 |
| `embed_model` | `string` | 현재 사용 중인 임베딩 모델명 |

---

## `POST /search`

질문과 가장 유사한 문서 청크를 반환합니다. LLM을 호출하지 않으며 검색 품질 확인·디버깅에 사용합니다.

### 요청

```json
{
  "question": "A형 간염 증상 알려줘."
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `question` | `string` | ✓ | 검색할 질문 |

### 응답 `200 OK`

```json
{
  "query": "A형 간염 증상 알려줘.",
  "hits": [
    {
      "source": "disease_info",
      "page": 2,
      "text": "A형 간염은 감염 후 약 30일의 잠복기를 거쳐 피로감, 메스꺼움, 구토, 식욕부진, 발열, 우측 상복부 통증 등 일차적인 전신증상이 나타난다."
    }
  ]
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `query` | `string` | 입력한 질문 그대로 |
| `hits` | `list` | 검색된 청크 목록 |
| `hits[].source` | `string` | 출처 파일명 |
| `hits[].page` | `int` | 페이지 번호 (1부터 시작) |
| `hits[].text` | `string` | 청크 본문 미리보기 (앞 120자) |

---

## `POST /ask`

검색된 건강정보을 근거로 LLM이 답변을 생성하고 출처를 함께 반환합니다. 문서에 근거가 없으면 답변을 생성하지 않고 회피합니다.

### 요청

```json
{
  "question": "A형 간염 증상 알려줘."
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `question` | `string` | ✓ | 답변을 요청할 질문 |

### 응답 `200 OK` — 근거 있음

```json
{
  "answer": "A형 간염은 감염 후 약 30일의 잠복기를 거쳐 피로감, 메스꺼움, 구토, 식욕부진, 발열, 우측 상복부 통증 등의 증상이 나타납니다.",
  "sources": ["disease_info p.1", "disease_info p.2"],
  "grounded": true
}
```

### 응답 `200 OK` — 근거 없음

```json
{
  "answer": 건강정보 문서에 없음",
  "sources": [],
  "grounded": false
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `answer` | `string` | 문서 근거 답변. 근거가 없으면 `"건강정보 문서에 없음"` |
| `sources` | `list[string]` | 출처 목록 (예: `"disease_info p.2"`). 근거 없으면 `[]` |
| `grounded` | `bool` | 근거로 답했으면 `true`, 회피면 `false` |

---

## 설계 원칙

- **`/search`와 `/ask` 분리** — 검색 품질과 LLM 품질을 독립적으로 점검할 수 있습니다.
- **Grounding 강제** — `/ask`는 검색된 청크 외의 정보로 답하지 않습니다. 근거가 없으면 `grounded: false`로 명시합니다.
- **LLM-free 엔드포인트** — `/health`와 `/search`는 LLM을 호출하지 않아 빠르고 비용이 없습니다.
- **임베딩 모델** — `jhgan/ko-sroberta-multitask` (한국어 특화 Sentence-BERT)
