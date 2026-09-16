# HEAPY 건강 AI 서비스

개인의 건강 기록과 공개 의료 지식을 활용해 상담과 건강 분석을 제공하는 FastAPI 서비스입니다. 기존 웹 챗봇·분석 데모와 모바일 백엔드 전용 내부 API를 함께 관리합니다.

[프로젝트 소개](https://github.com/Heapy-AI) · [모바일 앱](https://github.com/Heapy-AI/heapy-frontend) · [업무 백엔드](https://github.com/Heapy-AI/heapy-backend)

## 주요 기능

- 의료 질문 분류, 용어 정규화, 멀티턴 문맥 처리
- Pinecone의 공개 건강 지식 검색과 Gemini 기반 답변 생성
- 개인 건강 문맥을 반영한 상담, SSE 응답 스트리밍
- 건강검진 및 생활 건강 분석, 웹 데모와 개발자 모니터링 화면
- Spring Boot가 호출하는 내부 상담·건강 분석 API

## 실행 방식 구분

| 구분 | 진입점 | 용도 |
|---|---|---|
| 웹 데모 | `app.main:app` | 사용자 로그인, 챗봇·건강 분석 UI와 공개 데모 API |
| 내부 서비스 | `app.internal:app` | Spring Boot 전용 API. 현재 Docker 이미지의 실행 대상 |
| 개발자 UI | `run_admin_ui.py` | 웹 데모 서버와 연결하는 별도 모니터링 UI |

**현재 배포용 컨테이너는 웹 데모를 제공하지 않습니다.** 웹 화면을 확인하려면 `app.main:app`을 별도로 실행하세요. 내부 서버는 Swagger도 비활성화되어 있습니다.

## 기술과 처리 흐름

Python 3.11 · FastAPI · LangChain · Gemini · Sentence Transformers · Pinecone

```text
모바일 앱 → Spring Boot → FastAPI 내부 API
                           ├─ 전달받은 개인 건강 문맥
                           ├─ 질문 분류·의료 용어 처리
                           ├─ Pinecone 공개 지식 검색
                           └─ Gemini 생성 → 응답 / SSE

웹 데모 → Supabase 로그인 → 사용자별 기록 조회 → 상담·분석
```

모바일 경로의 인증·사용자 데이터 관리·일일 분석 일정과 결과 저장은 Spring Boot가 담당합니다. 웹 데모는 별도의 Supabase 인증·조회 경로를 사용합니다. 개인 건강 기록을 공개 지식 벡터 저장소에 적재하지 않습니다.

## 설치

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

```bash
# macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

운영 CPU 이미지의 고정 의존성 및 모델 캐시 구성은 [Dockerfile](Dockerfile)과 [requirements-deploy.txt](requirements-deploy.txt)에 있습니다. 첫 로컬 실행은 임베딩 모델 다운로드와 초기화 시간이 필요할 수 있습니다.

## 환경변수

프로젝트 루트 `.env`에 개발용 값을 설정합니다. 아래는 자리표시자이며 실제 키를 저장소에 올리지 않습니다.

```dotenv
GOOGLE_API_KEY=your-gemini-key
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX_NAME=your-index-name
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-publishable-key
AUTH_COOKIE_SECURE=0
SEARCH_COLLECTIONS=health_checkup_info,disease_info,medication_info,nutrient_info
```

- Gemini 키는 `GEMINI_API_KEY`도 지원합니다.
- 웹 데모 인증 키는 `SUPABASE_PUBLISHABLE_KEY` 또는 `SUPABASE_ANON_KEY`를 사용합니다.
- `AUTH_COOKIE_SECURE=0`은 로컬 HTTP용입니다. HTTPS에서는 `1`로 설정합니다.
- 내부 서버는 **32자 이상의 `INTERNAL_SERVICE_TOKEN`을 프로세스 환경변수로 먼저 설정**해야 합니다. Spring Boot의 `CHAT_INTERNAL_TOKEN`과 같은 값을 사용합니다. 이 토큰은 앱에 넣지 않습니다.
- 추가 설정과 기본값은 [app/core/config.py](app/core/config.py)를 기준으로 확인합니다.

## 실행

### 웹 데모

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 사용자 UI: <http://localhost:8000>
- API 문서: <http://localhost:8000/docs>

FastAPI가 정적 UI를 함께 제공합니다. 별도의 프론트엔드 개발 서버는 필요하지 않습니다. 로그인과 개인 기록 기능은 개발용 Supabase 설정 및 해당 스키마·권한 구성이 필요합니다.

### 내부 API

셸 또는 컨테이너 환경에 `INTERNAL_SERVICE_TOKEN`을 설정한 뒤 실행합니다.

```bash
python -m uvicorn app.internal:app --host 127.0.0.1 --port 8000
```

웹 데모와 동시에 띄우려면 서로 다른 포트를 지정합니다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/health/ready` | 모델과 상담 서비스 준비 상태 |
| POST | `/internal/chat/answer` | 상담 결과 일괄 반환 |
| POST | `/internal/chat/stream` | SSE 상담 스트리밍 |
| POST | `/internal/health/analyses` | 건강 분석 생성 |

내부 업무 API는 `Authorization: Bearer <INTERNAL_SERVICE_TOKEN>` 인증이 필요합니다. 모델 초기화가 끝나기 전에는 준비 상태 확인이 실패할 수 있습니다. 요청 계약은 [app/internal.py](app/internal.py)와 [app/health_analysis.py](app/health_analysis.py)를 참고하세요.

### 개발자 모니터링

웹 데모 서버를 `8000` 포트에 먼저 실행한 다음 별도 터미널에서 실행합니다.

```bash
python run_admin_ui.py
```

개발자 UI: <http://localhost:3000>. 사용자 데모와 연결하여 질문 분류, 검색 근거, 응답과 진단 정보를 확인합니다.

## 검색 데이터

임베딩은 `jhgan/ko-sroberta-multitask`, 차원은 `768`, 유사도는 `cosine`을 기준으로 구성합니다. 연결할 Pinecone 인덱스가 이 설정과 맞아야 합니다.

| 네임스페이스 | 내용 |
|---|---|
| `health_checkup_info` | 건강검진 항목·판정 기준 |
| `disease_info` | 질환·증상·예방 정보 |
| `medication_info` | 의약품·복약 정보 |
| `nutrient_info` | 영양성분 정보 |

원천 데이터 수집·정제와 VDB 적재 작업은 별도 관리합니다. 최신 적재 수량은 연결된 인덱스에서 확인합니다.

## 구조와 배포

| 경로 | 내용 |
|---|---|
| `app/core` | 설정, 모델 초기화, 공통 상태 |
| `app/routers`, `app/services`, `app/schemas` | 데모 API, 처리 로직, 데이터 계약 |
| `app/frontends` | 사용자·개발자 UI와 공용 이미지 |
| `app/internal.py`, `app/health_analysis.py` | 내부 상담·건강 분석 API |
| `model/classifier` | 의도 분류 모델 |
| `scripts/deploy` | 컨테이너 배포와 모델 캐시 도구 |
| `.github/workflows` | 소스 검증 및 개발 배포 |

```bash
docker build -t heapy-ai-health:local .
```

Docker는 CPU용 의존성과 모델 캐시를 준비하고 내부 서비스만 실행합니다. `dev` 푸시 시 검증이 실행되며, 저장소 변수 `DEPLOY_ENABLED=true`일 때 개발 배포가 진행됩니다. 이미지 게시와 EC2 배포는 기존 GitHub Actions·ECR·SSM 흐름을 사용합니다.

## 협업 문서

기능 브랜치에서 작업한 뒤 `dev`로 PR을 보냅니다. README는 공유 문서로 추적합니다. 로컬 `Reference`의 API 명세·아키텍처·화면 요구사항·DB 설계 및 제외된 개발 문서는 팀 공유 경로에서 전달받습니다. 실행 방법은 이 README와 실제 코드로 확인할 수 있도록 유지합니다.

<!-- 작성자: 김진우 -->
