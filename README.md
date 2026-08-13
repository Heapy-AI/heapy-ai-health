# 💊 HEAPY 건강정보 챗봇

> 사용자의 건강검진 데이터와 전문 의료정보를 함께 활용해 답변하는 FastAPI 기반 건강정보 챗봇입니다.
---

## 📌 프로젝트 개요
| 항목 | 내용 |
|------|------|
| **기간** | '26.07 ~'26.08 (6주) |
| **팀** | KT tech-up 생성형AI 1팀 TeamHP (4인) |
| **목표** | 의료 문서 + 개인데이터 → 맞춤 전문 답변 |
| **주요 모델** | Gemini 3.5 Flash |
| **최종 성능** | Test Accuracy **91.27%** |
---

## ✅ 주요 기능

- Supabase Auth 기반 회원가입, 로그인, 로그아웃 및 세션 복원
- 사용자별 대화 세션과 메시지·요약 저장
- 의료용어 정규화와 멀티턴 후속 질문 재작성
- `simple_lookup`, `comprehensive`, `general_chat`, `ignore` Intent별 처리
- 개인 건강 질문에 Supabase 건강검진 결과와 Pinecone 의료 근거 결합
- SSE 기반 답변 스트리밍

## 📱 운영 UI
<table>
  <tr>
    <td align="center"><img src="docs/ui_image/heapy_ui_00.png" width="500"></td>
    <td align="center"><img src="docs/ui_image/heapy_ui_01.png" width="500"></td>
  </tr>
    <tr>
    <td align="center"><img src="docs/ui_image/heapy_ui_02.png" width="500"></td>
    <td align="center"><img src="docs/ui_image/heapy_ui_03.png" width="500"></td>
  </tr>
</table>

## 📁 운영 구조

```text
heapy-ai-health/
├── app/
│   ├── core/                # 설정 및 애플리케이션 상태
│   ├── frontends/
│   │   ├── user/           # 사용자 UI
│   │   └── shared/         # 공용 이미지
│   ├── routers/            # 인증·대화·챗봇 API
│   ├── schemas/            # API 요청·응답 스키마
│   ├── services/           # 챗봇 파이프라인과 외부 저장소 연동
│   └── main.py             # FastAPI 진입점
├── database/
│   └── migrations/         # Supabase 스키마·RLS 마이그레이션
├── model/
│   └── classifier/
│       └── artifacts/
│           └── intent-v7/  # 운영 Intent 모델
├── docs/ui_image           # 운영 UI
├── requirements.txt
├── LICENSE
└── README.md
```

## ⚙️ 환경변수

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=heapy-rag
GOOGLE_API_KEY=your_gemini_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your_publishable_key
AUTH_COOKIE_SECURE=0
SEARCH_COLLECTIONS=health_checkup_info,disease_info,medication_info
```

- `SUPABASE_PUBLISHABLE_KEY` 대신 기존 `SUPABASE_ANON_KEY`도 사용할 수 있습니다.
- 로컬 HTTP 환경에서는 `AUTH_COOKIE_SECURE=0`, HTTPS 운영 환경에서는 `1`로 설정합니다.
- `.env`와 API 키는 Git에 커밋하지 않습니다.

## 🚀 설치 및 실행

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

macOS 또는 Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- 사용자 UI: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>

FastAPI가 사용자 UI와 API를 함께 제공합니다. 별도의 프런트엔드 서버는 필요하지 않습니다.

## 🔗 사용자 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/auth/signup` | 회원가입 및 사용자 프로필 생성 |
| `POST` | `/auth/login` | 로그인 및 HttpOnly 인증 쿠키 발급 |
| `GET` | `/auth/me` | 현재 로그인 사용자 조회 |
| `POST` | `/auth/refresh` | 로그인 세션 갱신 |
| `POST` | `/auth/logout` | 로그아웃 및 인증 쿠키 제거 |
| `GET` | `/conversations` | 현재 사용자의 대화 세션 목록 조회 |
| `POST` | `/conversations` | 새 대화 세션 생성 |
| `GET` | `/conversations/{session_id}` | 세션과 저장 메시지 조회 |
| `DELETE` | `/conversations/{session_id}` | 대화 세션 삭제 |
| `POST` | `/chat` | 통합 챗봇 응답 생성 |
| `POST` | `/chat/stream` | SSE 기반 통합 챗봇 응답 스트리밍 |

## 📦 Supabase 마이그레이션

`database/migrations/`는 서버 요청 처리 중 직접 실행되지는 않지만, 운영 DB 스키마와 RLS 정책을 재현하고 변경 이력을 관리하기 위해 유지합니다.

마이그레이션은 파일 번호 순서대로 Supabase SQL Editor 또는 배포 파이프라인에서 적용합니다. 기존 `public.users` 데이터는 삭제하지 않습니다.

## ⚠️ 운영 주의사항

- 개인 건강검진 데이터는 로그인 사용자의 Supabase access token과 RLS 정책을 통해서만 조회합니다.
- 서비스에서 사용하는 Intent v7 모델 파일을 삭제하거나 경로를 변경하지 않습니다.
- `SEARCH_COLLECTIONS`에는 실제 Pinecone namespace를 명시합니다.
- 개발자 UI, 평가 결과, 테스트 및 개발 문서는 `dev` 브랜치에서 관리합니다.
