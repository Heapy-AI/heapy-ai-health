# HEAPY 의료 검색 정규화 개선

`resolver` 브랜치를 기준으로 의료 검색어의 초성·오타·문맥을 처리하고, 불확실한 검색어를 사용자 확인 후 표준용어로 연결하는 작업 브랜치입니다.

## 주요 변경사항

- 특정 의료용어를 코드에 직접 매핑하지 않고, 원천 DB에서 생성한 표준용어·alias catalog를 기준으로 검색합니다.
- `ㄱㅅㅊ`, `ㅈㅎㅇ`, `갼슈치`처럼 초성 또는 오타가 포함된 검색어를 표준용어 후보로 변환합니다.
- 조사와 문장 성분을 분리하되 `나왔어`, `낮게`, `알려줘` 같은 동사·형용사는 의료용어 후보에서 제외합니다.
- 후보가 불확실하면 `혹시 '간수치'를 물어보신 걸까요?`와 같이 가장 유력한 후보 한 가지만 확인합니다.
- 확인 UI는 `예/아니요` 버튼으로 동작합니다.
- `예`를 선택하면 `confirmation_id`로 확정된 용어를 바로 사용하고, 원문을 다시 fuzzy 검색하지 않습니다.
- 표준용어 해석 결과를 RDB 검색, Pinecone 검색, LLM 응답 단계가 공유하도록 연결했습니다.
- 문서 토큰과 검색 결과를 캐시·인덱싱해 반복 검색과 중복 resolver 호출을 줄였습니다.
- RDB·Pinecone 없이도 로컬 서버에서 동일한 검색·확인·답변 흐름을 테스트할 수 있습니다.

## 검색 처리 흐름

```text
사용자 질문
  → 문장 정규화·조사 분리
  → 표준용어·alias 기준 초성/오타 후보 검색
  → 동사·형용사 문맥 후보 제거
  → 확정 후보면 바로 검색
  → 불확실하면 예/아니요 확인
  → RDB/Pinecone 검색 및 LLM 응답
```

## 주요 변경 파일

| 영역 | 파일 | 설명 |
|---|---|---|
| 검색 정규화 | [`app/services/query_resolver.py`](app/services/query_resolver.py) | 표준용어 기준 초성·오타·alias 후보 생성, 조사 분리, 문맥 후보 필터링 |
| 용어 catalog | [`app/services/medical_term_catalog.py`](app/services/medical_term_catalog.py) | 원천 JSONL에서 표준용어와 alias catalog 생성 |
| 확인 상태 | [`app/services/query_confirmation.py`](app/services/query_confirmation.py) | `confirmation_id` 생성·저장·소비·만료 처리 |
| 응답 orchestration | [`app/services/chat_orchestrator.py`](app/services/chat_orchestrator.py) | 확정 용어를 재검색하지 않고 검색·LLM 응답 단계로 전달 |
| Chat API | [`app/routers/chat.py`](app/routers/chat.py), [`app/schemas/health_chatbot.py`](app/schemas/health_chatbot.py) | 확인 ID와 `confirmation_answer` 처리 |
| 로컬 서버 | [`app/local_dev_server.py`](app/local_dev_server.py), [`app/services/local_dev.py`](app/services/local_dev.py) | 로컬 문서 인덱스, 검색 캐시, 테스트용 서버 |
| Pinecone 연결 | [`app/services/vector_search.py`](app/services/vector_search.py) | 정규화 결과 공유 및 중복 resolver 호출 방지 |
| Supabase migration | [`supabase/migrations/202608110001_medical_term_search.sql`](supabase/migrations/202608110001_medical_term_search.sql) | 표준용어·alias 테이블, 초성 검색 함수, trigram 인덱스와 Trigger 생성 |
| alias 적재 | [`database/build_medical_term_catalog.py`](database/build_medical_term_catalog.py) | 원천 JSONL을 Supabase 적재용 표준용어·alias SQL로 변환 |
| 웹 UI | [`app/web/assets/app.js`](app/web/assets/app.js), [`app/web/index.html`](app/web/index.html), [`app/web/assets/styles.css`](app/web/assets/styles.css) | `예/아니요` 확인 버튼과 confirmation ID 전송 |
| 기존 질의 연결 | [`app/routers/ask.py`](app/routers/ask.py), [`app/routers/intent.py`](app/routers/intent.py), [`app/services/safety_guard.py`](app/services/safety_guard.py) | 기존 질의·의도·안전 처리와 정규화 결과 연결 |
| 설정·스키마 | [`app/core/config.py`](app/core/config.py), [`app/main.py`](app/main.py), [`app/schemas/intent.py`](app/schemas/intent.py) | RDB/Pinecone/LLM 설정과 응답 구조 확장 |
| 테스트 | [`tests/test_query_resolver.py`](tests/test_query_resolver.py), [`tests/test_query_confirmation.py`](tests/test_query_confirmation.py), [`tests/test_local_dev.py`](tests/test_local_dev.py), [`tests/test_web_ui.py`](tests/test_web_ui.py) | 초성·오타·문맥 분리·확인 ID·로컬 UI 회귀 검증 |

## 로컬 검증

관련 테스트 42건이 통과했습니다.

```bash
GOOGLE_API_KEY=local-demo-key \
PYTHONDONTWRITEBYTECODE=1 \
python3 -m unittest \
  tests/test_query_resolver.py \
  tests/test_query_confirmation.py \
  tests/test_local_dev.py \
  tests/test_chat_orchestrator.py \
  tests/test_chat_stream.py \
  tests/test_web_ui.py
```

로컬 서버 실행:

```bash
GOOGLE_API_KEY=local-demo-key \
PYTHONPATH=. python3 -m uvicorn app.local_dev_server:app \
  --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000/`을 열고 `ㄱㅅㅊ` 입력 후 `예`를 선택하면 간수치 관련 답변 흐름을 확인할 수 있습니다.

## 관련 문서

- [`QUERY_NORMALIZATION_README.md`](QUERY_NORMALIZATION_README.md): 정규화 규칙, API 요청 예시, RDB/Pinecone 운영 연동
- [`supabase/README.md`](supabase/README.md): Supabase migration 적용과 alias 데이터 적재 순서
- 브랜치: [`feat/query-normalization`](https://github.com/Heapy-AI/heapy-ai-health/tree/feat/query-normalization)
