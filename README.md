# HEAPY 건강정보 RAG

한국어 건강정보 청크를 로컬에서 임베딩하고 Pinecone에서 검색하는 FastAPI RAG 서버입니다.

## 아키텍처

```text
data/ 원천 데이터
  → preprocessed/ 전처리
  → vdb/chunk/ JSONL 청크
  → jhgan/ko-sroberta-multitask 로컬 임베딩(768차원)
  → Pinecone dense index
  → namespace별 검색
  → FastAPI /search, /ask
  → FastAPI 시연용 웹 앱
```

| 컬렉션 | Pinecone namespace | 적재 대상 |
|---|---|---:|
| 건강검진정보 | `health_checkup_info` | 30건 |
| 질병정보 | `disease_info` | 54,330건 |
| 복약정보 | `medication_info` | 43,330건 |

`disease_info`는 JSONL 108,662행에서 ID 중복과 Base64 이미지 청크를 제외한 수치입니다.

현재 checkout의 `vdb/chunk`를 실제로 확인할 때는 `health_checkup_info=30`,
`disease_info=15,349`, `medication_info=0`입니다. 위 표의 복약 수치는 운영 적재
목표치이며, 복약 JSONL을 준비해 Pinecone에 적재하기 전까지는 해당 namespace가
비어 있으므로 약물 질문을 근거 기반으로 답할 수 없습니다.

## 환경

- Python `3.11.9`
- 임베딩 모델 `jhgan/ko-sroberta-multitask`
- 벡터 차원 `768`
- 거리 측정 `cosine`
- Pinecone Serverless `aws / us-east-1`

## 설치

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

프로젝트 루트의 `.env`:

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=heapy-rag
GOOGLE_API_KEY=your_gemini_api_key
# 선택: 오타·별칭을 RDB 표준용어로 연결
RDB_DSN=postgresql://user:password@host:5432/database
```

RDB 표준용어 정규화는 `database/migrations/001_medical_term_search.sql`을
적용한 뒤 활성화됩니다. RDB가 없거나 `RDB_DSN`이 비어 있으면 기존 Pinecone
검색을 그대로 사용하며, 설정된 경우 `/search`·`/ask`·`/chat` 응답의
`resolved_query`와 `resolved_terms`에서 보정 결과를 확인할 수 있습니다.
자세한 운영 규칙은 [`QUERY_NORMALIZATION_README.md`](QUERY_NORMALIZATION_README.md)를
참고하세요.

표준용어와 alias는 원천 JSONL에서 자동 생성합니다. 특정 의료용어를 검색 코드에
직접 매핑하지 않습니다.

```bash
python database/build_medical_term_catalog.py \
  --chunk-root vdb/chunk > /tmp/medical_term_catalog.sql
psql "$RDB_DSN" -f /tmp/medical_term_catalog.sql
```

로컬 서버도 같은 catalog 생성기를 사용하므로, `vdb/chunk`가 없을 때는 의료용어
fixture로 대체하지 않고 근거 없음으로 처리합니다. `resolved_query`와
`resolved_terms` 외에 `resolution_status`가 `RESOLVED`, `CONFIRM`,
`AMBIGUOUS`, `NO_MATCH` 중 하나로 반환됩니다.
초성·오타 확인 응답에는 `confirmation_id`가 함께 반환되며, 사용자가 `예`를
선택하면 이 ID로 확인된 표준용어를 확정합니다. 원문을 다시 전체 fuzzy 검색하지
않으므로 문장 속 동사·형용사가 새로운 의료용어로 오인되지 않습니다.

기존 통합 임베딩 인덱스는 768차원 로컬 임베딩과 호환되지 않습니다. 별도의 `heapy-rag` dense 인덱스를 사용합니다.

## Pinecone 최초 적재

768차원 dense 인덱스 생성:

```powershell
python vdb/script/manage_pinecone.py create-index
```

청크 검증:

```powershell
python vdb/script/manage_pinecone.py ingest `
  --collection health_checkup_info `
  --dry-run

python vdb/script/manage_pinecone.py ingest `
  --collection disease_info `
  --dry-run
```

적재:

```powershell
python vdb/script/manage_pinecone.py ingest `
  --collection health_checkup_info

python vdb/script/manage_pinecone.py ingest `
  --collection disease_info
```

적재 상태:

```powershell
python vdb/script/manage_pinecone.py stats
```

검색 확인:

```powershell
python vdb/script/manage_pinecone.py search `
  --collection health_checkup_info `
  --query "건강검진 정상B는 무슨 뜻이야?"
```

## 추가 데이터 동기화

신규 원천을 기존 코드로 전처리·청킹한 뒤 같은 명령을 다시 실행합니다.

```powershell
python vdb/script/manage_pinecone.py ingest `
  --collection disease_info
```

로컬 manifest의 `record_sha256`과 비교해 본문 또는 메타데이터가 바뀐 청크만 임베딩하고 upsert합니다. 성공한 배치마다 manifest를 저장하므로 중단 후 같은 명령을 실행하면 완료된 청크는 건너뜁니다.

원천에서 삭제된 청크도 Pinecone에서 제거할 때만 `--delete-stale`을 사용합니다.

```powershell
python vdb/script/manage_pinecone.py ingest `
  --collection disease_info `
  --delete-stale
```

전체 재임베딩이 필요할 때:

```powershell
python vdb/script/manage_pinecone.py ingest `
  --collection disease_info `
  --force
```

이미 임베딩된 e약은요 compact 패키지는 재임베딩하지 않고 직접 적재합니다.

```powershell
python vdb/script/manage_pinecone.py ingest-precomputed `
  --source data/eyak/eyak `
  --collection medication_info `
  --batch-size 100
```

## 서버 실행

FastAPI:

```powershell
uvicorn app.main:app --reload
```

- 웹 앱: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>

별도의 프론트엔드 개발 서버 없이 FastAPI가 시연용 웹 앱을 함께 제공합니다.
웹 앱은 통합 챗봇 `POST /chat/stream`을 사용하며 Intent, 근거 검증, 출처 정보를
시각적으로 확인할 수 있습니다. 현재 복약 데이터는 검토 중 상태로 표시됩니다.

Gradio:

```powershell
python run_ui.py
```

- UI: <http://localhost:7860>

Gradio 화면은 검색 품질 점검용으로 유지하며, 실제 MVP 시연은 FastAPI 웹 앱을
사용합니다.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/health` | Pinecone namespace별 적재 수 확인 |
| `POST` | `/chat/stream` | SSE 기반 통합 챗봇 토큰 스트리밍 |
| `POST` | `/search` | 로컬 질문 임베딩 후 Pinecone 검색 |
| `POST` | `/ask` | 검색 청크 기반 Gemini 답변 |

자세한 내용은 `docs/api_spec.md`, `docs/GRADIO_GUIDE.md`를 참고합니다.

`/chat`·`/chat/stream` 요청에는 확인 흐름을 위한 선택 필드가 있습니다.

```json
{
  "question": "ㄱㅅㅊ",
  "confirmation_id": "서버가 발급한 ID",
  "confirmation_answer": true
}
```

## 로컬에서 실제 Gemini 답변 확인

외부 키 없이 실행하면 `app/local_dev_server.py`가 검색·오타 보정만 확인하는
`LOCAL_DEMO` 모드로 동작합니다. 실제 Gemini의 근거 계획·답변 생성·사후 감사까지
확인하려면 프로젝트 루트 `.env`에 `GOOGLE_API_KEY`를 설정하고 다음 명령을 실행합니다.

```bash
LOCAL_LLM_ENABLED=1 \
PYTHONPATH=. \
python3 -m uvicorn app.local_dev_server:app --host 127.0.0.1 --port 8000
```

이 모드는 Pinecone 대신 로컬 샘플 문서를 검색하므로 벡터 DB 키 없이도 LLM 답변
단계를 확인할 수 있습니다. 화면의 `Answer generation` 또는 `/health`의
`llm_backend`가 `GEMINI`인지 확인하세요.

## 운영 주의사항

- `.env`, API Key, Gemini Key를 Git에 커밋하지 않습니다.
- 개인 검진 수치와 식별정보를 공용 namespace에 적재하지 않습니다.
- 청크 ID는 재실행과 갱신을 위해 안정적으로 유지합니다.
- `--delete-stale`은 전체 원천 청크가 준비된 상태에서만 사용합니다.
- 로컬 manifest는 적재 체크포인트이며 `vdb/manifest/`에 생성됩니다.

## 참고 자료

- Pinecone create index: <https://docs.pinecone.io/guides/index-data/create-an-index>
- Pinecone upsert: <https://docs.pinecone.io/guides/index-data/upsert-data>
- Pinecone namespaces: <https://docs.pinecone.io/guides/index-data/implement-multitenancy>
