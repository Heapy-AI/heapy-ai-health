# Gradio UI 사용 가이드

## 개요

**HEAPY 건강정보 RAG** 서빙 시스템의 Gradio 기반 웹 인터페이스입니다.
검색(임베딩)과 답변(LLM)을 분리한 설계이며, 여러 **지식베이스 컬렉션**을 선택해 질의합니다.

**3개의 탭**:
1. 🔍 **Health**: 서버·컬렉션별 인덱스 상태 점검
2. 🔎 **Search**: 유사 청크 검색 (LLM 호출 없음)
3. 💬 **Ask**: 지식베이스 근거 답변 생성 (LLM 호출)

### 컬렉션(지식베이스)

| 컬렉션 | 내용 | 청크 수(현재) |
|--------|------|-----------|
| `health_checkup_info` | 국가건강검진 핵심항목 설명 (SOURCE_VERIFIED) | 30 |
| `disease_info` | AIHub 의학지식 QA + 질병관리청 국가건강정보포털 | 약 54,000 |
| `medication_info` | (예정: 병용금기/DUR) | 미적재 |

> 각 컬렉션은 chroma에서 독립된 네임스페이스이며, 요청마다 하나를 지정합니다.

---

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (Ask 탭에서만 필요)

임베딩·검색(Health/Search)은 API 키가 필요 없습니다.
**답변 생성(Ask)** 은 Gemini를 쓰므로 키가 필요합니다.

```bash
# .env 예시 — 둘 중 하나
GEMINI_API_KEY=your_key_here
# 또는
GOOGLE_API_KEY=your_key_here
```

---

## 실행

### 터미널 1: FastAPI 서버 실행

```bash
uvicorn app.main:app --reload
```

- 🟢 서버 시작: `http://localhost:8000`
- API 문서: `http://localhost:8000/docs` (Swagger UI)
- 서버 시작 시 컬렉션별 인덱스를 열고 준비합니다(이미 적재돼 있으면 재인덱싱 없이 열기만 함).

### 터미널 2: Gradio UI 실행

```bash
python run_ui.py
```

- 🟢 UI 시작: `http://localhost:7860`
- UI는 시작 시 `/health`에서 사용 가능한 컬렉션 목록을 가져와 드롭다운을 채웁니다.

---

## 각 탭 설명

### 🔍 Health 탭

서버와 컬렉션별 인덱스 상태를 확인합니다. LLM을 호출하지 않습니다.

**요청**: "상태 확인" 버튼 클릭

**응답 예시**:
```
Status: ok
Ready: ✅ 준비 완료
임베딩 모델: jhgan/ko-sroberta-multitask
컬렉션별 인덱스:
  - health_checkup_info: 30개
  - disease_info: 54,331개
```

---

### 🔎 Search 탭

LLM 없이 임베딩 검색만 수행합니다.

**입력**: **컬렉션 선택** + 질문 (예: "감기 원인이 뭐야?", "공복혈당 정상 수치는?")

**출력**:
- 검색된 청크 (상위 3개)
- 각 청크의 **출처(`라벨 · URL`)** 와 본문 미리보기
- JSON 응답 (디버깅용)

**장점**: 빠름 · 비용 0(LLM 없음) · 검색 품질 디버깅에 유용

---

### 💬 Ask 탭

검색된 청크를 근거로 LLM이 답변을 생성합니다.

**입력**: **컬렉션 선택** + 질문

**출력**:
- AI 답변 (끝에 "이 답변은 의료 진단이 아닌 정보 제공 목적입니다" 고지 포함)
- 상태 배지:
  - ✅ **근거 있음**
  - ⚠️ **근거 없음**: 지식베이스에 근거가 없으면 `지식베이스에 근거 없음`으로 회피
- 출처 목록 (예: `AIHub 전문 의학지식 데이터 · https://...`, `질병관리청 국가건강정보포털 · https://...`)

**특징**: Grounding 강제(검색된 청크만 근거) · 근거 없으면 추측 안 함 · LLM 비용 발생

---

## 기능

- **Enter 키 전송**: Search/Ask 텍스트박스에서 Enter로 즉시 요청
- **JSON 응답 확인**: 우측 패널에 원본 JSON 표시(검증·디버깅용)
- **에러 처리**: 서버 미연결/타임아웃 시 명확한 오류 메시지

---

## 트러블슈팅

### ❌ "오류: Connection refused"
**원인**: FastAPI 서버 미실행 → `uvicorn app.main:app --reload`

### ❌ 서버 시작 시 `RuntimeError: ...원천 파일을 찾지 못했습니다`
**원인**: `COLLECTIONS`에 등록됐지만 아직 적재/원천이 없는 컬렉션(예: `medication_info`)을 서버가 빌드하려다 실패.
**해결**: 해당 컬렉션을 적재하거나, `app/core/config.py`의 `COLLECTIONS`에서 임시로 제외.

### ❌ Health에서 특정 컬렉션이 `0개`
**원인**: 아직 적재되지 않음.
**해결**: 적재 스크립트 실행 (아래 참조).

### ⚠️ 검색 결과가 부정확
- Search 탭으로 먼저 검색 품질 확인 → 질문 키워드 조정
- 질문에 맞는 컬렉션을 선택했는지 확인(검진 vs 질병)

---

## 지식베이스 적재 (참고)

UI/서버는 이미 적재된 `vdb/chroma`를 사용합니다. 새로 적재하려면:

```bash
# 컬렉션 적재 (LLM 키 불필요, 임베딩만)
python vdb/script/ingest_vdb.py --collection health_checkup_info
python vdb/script/ingest_vdb.py --collection disease_info --rebuild
```

적재 대상 청크는 `vdb/chunk/<컬렉션>/*.jsonl`에서 읽습니다.
전처리→청크 생성 파이프라인은 `preprocessed/script/`에 있습니다.

---

## API 엔드포인트

| 메서드 | 경로 | 설명 | 필수 필드 | LLM |
|--------|------|------|----------|-----|
| `GET` | `/health` | 서버·컬렉션별 인덱스 상태 | — | ✗ |
| `POST` | `/search` | 유사 청크 검색 | `question`, `collection` | ✗ |
| `POST` | `/ask` | 지식베이스 근거 답변 | `question`, `collection` | ✓ |

**요청 예시**:
```json
{ "question": "감기 원인이 뭐야?", "collection": "disease_info" }
```

**API 문서**: `http://localhost:8000/docs`

---

## 파일 구조

```
heapy-ai-health-main/
├── app/
│   ├── main.py              # FastAPI 앱(lifespan에서 컬렉션 인덱스 준비)
│   ├── ui.py                # Gradio UI (이 문서 대상)
│   ├── core/
│   │   ├── config.py        # 설정(COLLECTIONS, PERSIST_DIR, 임베딩 모델)
│   │   └── state.py         # 서버 상태
│   ├── routers/ask.py       # /health /search /ask 엔드포인트
│   ├── schemas/health_chatbot.py # 건강관리 챗봇 요청/응답 스키마
│   └── services/rag.py      # 인덱싱·검색·RAG 체인, 출처 표기(cite)
├── data/                    # ① 원천(raw)
│   ├── disease_info/        #   AIHub QA + KDCA API xlsx
│   └── health_checkup_info/ #   건강검진 패키지
├── preprocessed/            # ② 전처리 산출물(검수 가능)
│   ├── disease_info/{aihub,kdca}/
│   └── script/              #   전처리·청킹 스크립트
├── vdb/
│   ├── chunk/<컬렉션>/       # ③ 청크(.jsonl, {text, metadata})
│   ├── chroma/              # ④ chroma 벡터 인덱스(영속화)
│   └── script/ingest_vdb.py #   적재 스크립트
├── run_ui.py                # Gradio UI 실행
└── requirements.txt
```

---

## 개발자 참고

### 커스터마이징 (`app/ui.py`)

```python
API_BASE_URL = "http://localhost:8000"   # API 주소
FALLBACK_COLLECTIONS = ["disease_info", "health_checkup_info"]  # /health 실패 시 기본 목록
# 포트 변경: create_ui().launch(server_port=7860)
```

### 새 컬렉션을 UI에 노출
컬렉션 드롭다운은 `/health`의 `indexed_chunks` 키에서 자동 생성됩니다.
새 컬렉션을 적재하고 `config.py`의 `COLLECTIONS`에 등록하면 UI에도 자동 반영됩니다.

---

## 보안 주의사항

⚠️ **프로덕션 배포 시**:
1. **CORS**: API 서버 CORS 정책 설정
2. **인증/레이트 리미팅**: `/ask`(LLM 비용) 보호
3. **HTTPS** 사용
4. **개인 건강정보**: 개인 검진 수치·식별정보는 VDB에 넣지 않음(데이터 계약 준수)
5. **의료 고지**: 답변은 정보 제공 목적이며 진단·처방이 아님

---

HEAPY 건강정보 RAG
