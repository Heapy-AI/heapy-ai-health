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
  → Supabase Auth 로그인 및 사용자별 대화 세션 로드
  → 멀티턴 후속 질문 재작성 및 RDB 의료용어 정규화
  → 설정된 전체 namespace 병렬 검색·근거 검사
  → FastAPI /search, /ask
  → FastAPI 개발자 모니터링 UI 및 사용자 UI
```

| 컬렉션 | Pinecone namespace | 적재 대상 |
|---|---|---:|
| 건강검진정보 | `health_checkup_info` | 30건 |
| 질병정보 | `disease_info` | 54,330건 |
| 복약정보 | `medication_info` | 43,330건 |

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
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your_publishable_key
AUTH_COOKIE_SECURE=0
```

`SUPABASE_PUBLISHABLE_KEY` 대신 레거시 `SUPABASE_ANON_KEY`도 사용할 수 있습니다.
로컬 HTTP에서는 `AUTH_COOKIE_SECURE=0`, HTTPS 운영 환경에서는 반드시 `1`로 설정합니다.
설정이 완료되면 웹 앱은 Supabase 이메일·비밀번호 로그인을 먼저 요구하고, 인증 세션은
JavaScript에서 읽을 수 없는 HttpOnly 쿠키로 유지합니다.
회원가입 시 `auth.users` 계정과 같은 UUID의 `public.users` 프로필이 생성됩니다. 대화는
`chat_sessions`, `chat_messages`에 사용자별로 저장되며 RLS가 다른 사용자의 접근을 막습니다.
기존 `public.users` 데이터는 마이그레이션에서 삭제하거나 변경하지 않습니다.

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

- 사용자 UI: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>

별도의 프론트엔드 개발 서버 없이 FastAPI가 사용자 UI를 함께 제공합니다.
웹 앱은 통합 챗봇 `POST /chat/stream`을 사용하며 Intent, 근거 검증, 출처 정보를
시각적으로 확인할 수 있습니다. 현재 복약 데이터는 검토 중 상태로 표시됩니다.

기본 Intent 모델은 `classifier/artifacts/intent-v7/best_model.json`입니다. v7에서는
`ignore`를 건강 서비스 외 질문으로 한정하고, 의료 위험 질문은 Safety Guard가
Intent를 바꾸지 않은 채 위험 수준과 금지 행동을 최종 프롬프트에 전달합니다.

개발자 모니터링 UI:

```powershell
python run_admin_ui.py
```

- 개발자 UI: <http://localhost:3000>
- API 서버: <http://localhost:8000>

개발자 UI는 사용자 서비스와 별도로 실행되며 프로젝트 환경, Intent·감사 로그,
검색 근거와 응답 원본 JSON을 표시합니다. 실행 전에 FastAPI 서버가 `8000` 포트에서
실행 중이어야 합니다. 회원가입·로그인·로그아웃 요청과 HttpOnly 인증 쿠키는 개발자
UI 서버가 메인 API로 중계하며, 사용자 UI와 동일한 Supabase 세션별 대화 저장을 사용합니다.

프런트엔드 정적 파일은 `app/frontends/admin`, `app/frontends/user`로 분리하며,
두 화면이 함께 사용하는 이미지는 `app/frontends/shared/images`에서 제공합니다.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/auth/signup` | 회원가입 및 사용자 프로필 생성 |
| `POST` | `/auth/login` | 로그인 및 HttpOnly 인증 쿠키 발급 |
| `POST` | `/auth/logout` | 로그아웃 및 인증 쿠키 제거 |
| `GET` | `/conversations` | 현재 사용자의 대화 세션 목록 |
| `POST` | `/conversations` | 새 대화 세션 생성 |
| `GET` | `/conversations/{session_id}` | 세션과 저장 메시지 조회 |
| `DELETE` | `/conversations/{session_id}` | 대화 세션 삭제 |
| `GET` | `/health` | Pinecone namespace별 적재 수 확인 |
| `POST` | `/chat/stream` | SSE 기반 통합 챗봇 토큰 스트리밍 |
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
