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
  → Gradio UI
```

| 컬렉션 | Pinecone namespace | 적재 대상 |
|---|---|---:|
| 건강검진정보 | `health_checkup_info` | 30건 |
| 질병정보 | `disease_info` | 54,330건 |

`disease_info`는 JSONL 108,662행에서 ID 중복과 Base64 이미지 청크를 제외한 수치입니다.

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
```

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

## 서버 실행

FastAPI:

```powershell
uvicorn app.main:app --reload
```

- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>

Gradio:

```powershell
python run_ui.py
```

- UI: <http://localhost:7860>

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/health` | Pinecone namespace별 적재 수 확인 |
| `POST` | `/search` | 로컬 질문 임베딩 후 Pinecone 검색 |
| `POST` | `/ask` | 검색 청크 기반 Gemini 답변 |

자세한 내용은 `docs/api_spec.md`, `docs/GRADIO_GUIDE.md`를 참고합니다.

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
