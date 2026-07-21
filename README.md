# HEAPY 건강정보 RAG

한국어 건강정보 질의응답을 위한 RAG(검색 증강 생성) 서버입니다.
**검색(임베딩)** 과 **답변(LLM)** 을 분리하고, 여러 **지식베이스 컬렉션**을 선택해 질의합니다.

> ⚠️ **의료 고지**: 본 시스템의 답변은 **정보 제공 목적**이며 의료 진단·치료·처방이 아닙니다.
> 개인 검진 수치·식별정보는 벡터DB에 저장하지 않습니다.

---

## 아키텍처

검색은 무료 한국어 임베딩(`jhgan/ko-sroberta-multitask`)으로, 답변은 Gemini로 생성합니다.
데이터는 **4단 파이프라인**으로 원천 → 전처리 → 청크 → 벡터인덱스 순으로 흐릅니다.

```
data/            ① 원천(raw)              원본 데이터 (읽기 전용)
  │  preprocessed/script/preprocess_*.py
  ▼
preprocessed/    ② 전처리(검수 가능)       정제·파싱된 중간 산출물
  │  preprocessed/script/chunk_disease.py
  ▼
vdb/chunk/       ③ 청크(.jsonl)           {text, metadata} 임베딩 단위
  │  vdb/script/ingest_vdb.py
  ▼
vdb/chroma/      ④ 벡터 인덱스            Chroma 영속화 (검색 대상)
```

- **원천/전처리/청크/인덱스 분리** → 청크 예산을 바꿔도 원천 재파싱 없이 재청킹 가능, 중간물 검수 용이
- **컬렉션은 독립 네임스페이스** → 요청마다 하나를 지정해 검색

---

## 지식베이스 컬렉션

| 컬렉션 | 내용 | 출처 | 규모(청크) |
|--------|------|------|-----------|
| `disease_info` | 의학지식 QA + 질병 설명 | AIHub 전문/필수의료 의학지식, 질병관리청 국가건강정보포털 | 54,331 |
| `health_checkup_info` | 국가건강검진 핵심항목 설명 | 보건복지부 건강검진 실시기준 등 (SOURCE_VERIFIED) | 30 |
| `medication_info` | 병용금기/DUR (예정) | 식약처 DUR | 미적재 |

> **`disease_info` 내역**: AIHub QA **31,032**(정제·병합) + KDCA 질병×섹션 **23,299**(크기적응형) = **54,331**
> **`health_checkup_info`**: SOURCE_VERIFIED 청크 **30**

---

## 검색 품질 점검

적재 후 실제 검색 결과(1순위, 괄호는 코사인 유사도). 한 컬렉션에서 AIHub·KDCA 두 소스가 정상 혼합 검색됨을 확인했습니다.

| 질의 | 컬렉션 | 1순위 결과 | 출처 |
|---|---|---|---|
| 감기 원인이 뭐야 | `disease_info` | 감기 · 요약문 (0.75) | 질병관리청 |
| 흡연이 건강에 미치는 영향 | `disease_info` | 흡연 · 건강에 미치는 영향 (0.82) | 질병관리청 |
| 제2형 당뇨병 초기 경구약 | `disease_info` | 내과 객관식 · 메트포르민 (0.85) | AIHub 필수의료 |
| 골절은 어떻게 치료하나요 | `disease_info` | 외과 · 골절 치료 (0.78) | AIHub 전문 |
| 요추 추간판 탈출증 초기 치료 | `disease_info` | 추간판탈출증 · 치료 + AIHub 혼합 (0.74) | 질병관리청·AIHub |
| 복부비만 허리둘레 기준 | `health_checkup_info` | 허리둘레 (0.71) | 건강검진 판정기준 |
| 공복혈당 정상 수치는 | `health_checkup_info` | 공복혈당 (0.60) | 건강검진 판정기준 |

> 정밀 질의는 정확한 섹션/항목을, 광범위 질의("감기 알려줘")는 KDCA `요약문` 청크를 회수합니다.

---

## 데이터 출처

- **AIHub 전문 의학지식 데이터** — <https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71874>
- **AIHub 필수의료 의학지식 데이터** — <https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71875>
- **질병관리청 국가건강정보포털** (API) — <https://health.kdca.go.kr/healthinfo>
- **보건복지부 건강검진 실시기준** 등 — `data/health_checkup_info/` 패키지 참고

---

## 디렉터리 구조

```
heapy-ai-health-main/
├── app/                      # FastAPI 서빙 앱
│   ├── main.py               #   lifespan에서 컬렉션 인덱스 준비
│   ├── ui.py                 #   Gradio 웹 UI
│   ├── core/{config,state}.py#   설정(COLLECTIONS·경로·모델)·전역 상태
│   ├── routers/ask.py        #   /health /search /ask
│   ├── schemas/cs.py         #   요청/응답 스키마
│   └── services/rag.py       #   인덱싱·검색·RAG 체인·출처표기(cite)
├── data/                     # ① 원천(raw)
│   ├── disease_info/         #   AIHub QA(.json) + KDCA API 목록(.xlsx)
│   └── health_checkup_info/  #   건강검진 공유 패키지
├── preprocessed/             # ② 전처리 산출물
│   ├── disease_info/{aihub,kdca}/
│   └── script/               #   preprocess_disease_aihub.py · preprocess_kdca.py · chunk_disease.py
├── vdb/
│   ├── chunk/<컬렉션>/        # ③ 청크(.jsonl)
│   ├── chroma/               # ④ Chroma 벡터 인덱스
│   └── script/ingest_vdb.py  #   적재 스크립트
├── docs/                     # API 명세·UI 가이드
├── run_ui.py                 # Gradio UI 실행
└── requirements.txt
```

---

## 설치

가상환경은 **`health-ai/` (Python 3.11.9)** 를 사용합니다.

### Git LFS 준비
이 저장소는 큰 Chroma 인덱스 파일을 Git LFS로 관리합니다. 팀원이 저장소를 받는 절차는 아래와 같습니다.

```bash
# 1) Git LFS 설치 (macOS 예시)
brew install git-lfs
git lfs install

# 2) 저장소 클론
git clone https://github.com/Heapy-AI/heapy-ai-health.git
cd heapy-ai-health

# 3) LFS 파일 내려받기
git lfs pull
```

이미 저장소를 이미 클론했다면, LFS가 설치된 뒤에 아래만 실행하면 됩니다.

```bash
git lfs install
git lfs pull
```

### Python 의존성

```bash
# 의존성
pip install -r requirements.txt
pip install openpyxl          # KDCA xlsx 전처리에 필요

# 환경 변수 (답변 생성 /ask 에서만 필요, 검색/적재는 불필요)
# .env 에 둘 중 하나
GEMINI_API_KEY=your_key
# 또는
GOOGLE_API_KEY=your_key
```

---

## 데이터 파이프라인 (재현)

원천에서 벡터DB까지 재생성하려면 순서대로 실행합니다. (모두 LLM 키 불필요 — 임베딩만 사용)

```bash
# ② 전처리: 원천 → preprocessed/
python preprocessed/script/preprocess_disease_aihub.py   # AIHub QA 정제
python preprocessed/script/preprocess_kdca.py            # KDCA API fetch·파싱

# ③ 청킹: preprocessed/ → vdb/chunk/
python preprocessed/script/chunk_disease.py              # AIHub 병합 / KDCA 크기적응형

# ④ 적재: vdb/chunk/ → vdb/chroma/
python vdb/script/ingest_vdb.py --collection disease_info --rebuild
python vdb/script/ingest_vdb.py --collection health_checkup_info
```

### 청킹 전략
- **AIHub QA**: 1 QA = 1 청크 (질문+답변 병합). q_type별로 객관식 보기·정답 번호 제거.
- **KDCA**: 질병×섹션을 **크기 적응형**으로 청킹 — 작은 섹션 병합·큰 섹션 분할(임베딩 128토큰 창에 맞춤).

---

## 실행

```bash
# 터미널 1 — API 서버
uvicorn app.main:app --reload          # http://localhost:8000  (/docs 스웨거)

# 터미널 2 — Gradio UI
python run_ui.py                        # http://localhost:7860
```

> 서버는 시작 시 `COLLECTIONS`의 컬렉션을 엽니다. 미리 적재돼 있으면 재인덱싱 없이 열기만 합니다.
> 자세한 UI 사용법은 [docs/GRADIO_GUIDE.md](docs/GRADIO_GUIDE.md), API 명세는 [docs/api_spec.md](docs/api_spec.md) 참고.

---

## API 요약

| 메서드 | 경로 | 설명 | 필수 필드 | LLM |
|--------|------|------|----------|-----|
| `GET` | `/health` | 서버·컬렉션별 인덱스 상태 | — | ✗ |
| `POST` | `/search` | 유사 청크 검색 | `question`, `collection` | ✗ |
| `POST` | `/ask` | 근거 답변 + 출처 | `question`, `collection` | ✓ |

```json
POST /ask
{ "question": "감기 원인이 뭐야?", "collection": "disease_info" }
```

- **Grounding 강제**: 검색된 청크에 근거가 없으면 `지식베이스에 근거 없음`으로 회피(`grounded: false`).
- **출처 표기**: 두 컬렉션 공통 `라벨 · URL` 형식 (예: `AIHub 전문 의학지식 데이터 · https://...`).

---

## 청크 메타데이터

컬렉션별 facet은 다르지만 **`source`(URL)·`source_label`·`review_status`** 는 공통 키로 정렬되어
출처 표기와 거버넌스 필터가 일관됩니다.

| 컬렉션 | 주요 메타 |
|--------|-----------|
| `disease_info` (AIHub) | `qa_id`, `specialty`(진료과), `q_type`, `review_status=UNVERIFIED_AIHUB` |
| `disease_info` (KDCA) | `disease`, `section`, `superclass`, `cntnts_sn`, `review_status=SOURCE_VERIFIED` |
| `health_checkup_info` | `canonical_key`, `heading`, `domain`, `corpus_version`, `review_status=SOURCE_VERIFIED` |

---

## 한계 및 주의

- **임상 미검수**: AIHub QA는 `UNVERIFIED_AIHUB`. 실서비스 전 의료진 검수 필요.
- **임베딩 창 128토큰**: 긴 본문은 임베딩 시 앞부분만 반영(전문은 `page_content`에 보존).
- **KDCA 공백 13건**: 천식·위염·대사증후군 등은 API가 빈 콘텐츠를 반환해 제외됨(원천 공백).
- **medication_info 미적재**: `COLLECTIONS`에서 활성화 전 주석 처리(서버 기동 크래시 방지).
- **개인정보**: 개인 검진 수치·주민번호 등은 VDB에 넣지 않음(데이터 계약 준수).

---

## 라이선스

[LICENSE](LICENSE) 참고.
