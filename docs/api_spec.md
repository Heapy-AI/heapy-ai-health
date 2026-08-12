# HEAPY API 명세서

- 작성자: 김진우
- Base URL: `http://localhost:8000`
- 검색 저장소: Pinecone
- 임베딩 모델: `jhgan/ko-sroberta-multitask` 768차원
- 기본 Intent 체크포인트: `classifier/artifacts/intent-v7/best_model.json`

## 공통 처리 흐름

```text
사용자 질문
→ 대화 이력·요약을 사용한 후속 질문 독립형 재작성
→ RDB 의료용어 정규화 및 필요 시 사용자 확인
→ 정규화 질문 임베딩 및 Intent v7 분류
→ 원문·정규화 질문의 Safety Guard 정책 병합
→ Intent별 처리
  ├─ simple_lookup: Pinecone 병렬 검색
  ├─ comprehensive: 질문 관련 개인 검진 RDB 조회 + Pinecone 병렬 검색
  ├─ general_chat: 검색 없는 일반 대화
  └─ ignore: 건강 서비스 외 고정 응답
→ 검색 결과 기본 검사
→ 근거가 있는 항목만 최종 답변 생성·스트리밍
→ 사후 감사 및 개발자 모니터링 기록
```

Safety Guard는 Intent를 변경하지 않는다. 다음 정보만 생성해 최종 답변 프롬프트의
허용 범위를 제한한다.

- `risk_level`: `normal`, `caution`, `emergency`. 위험 단어 하나가 아니라 위험 증상,
  개인·현재 상황, 즉시 행동 요청, 일반 정보형 의문문을 함께 판정한다.
- `restricted_actions`: 확정 진단, 개인 처방, 복용량 변경, 복약 중단, 내원 여부 결정
- `response_policy`: 일반 근거 답변, 제한된 안전 안내, 긴급 안내 우선
- `emergency`: 긴급 안내 우선 여부

## `GET /`

FastAPI와 함께 실행되는 개발·검증용 웹 앱을 반환한다. 중앙에는 챗봇, 왼쪽에는
프로젝트 환경, 오른쪽에는 질문별 검색 결과 검사·안전 정책·사후 감사·원본 JSON을
표시한다.

## 인증 API

Supabase Auth의 이메일·비밀번호 인증을 사용한다. 로그인 성공 시 access token과 refresh
token은 응답 본문에 노출하지 않고 `HttpOnly`, `SameSite=Lax` 쿠키로 저장한다. Supabase가
설정된 환경에서는 `POST /chat`, `POST /chat/stream` 호출에 유효한 로그인 세션이 필요하다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/auth/signup` | Auth 계정과 `public.users` 프로필 생성 및 가능한 경우 인증 쿠키 발급 |
| `POST` | `/auth/login` | 이메일·비밀번호 로그인 및 인증 쿠키 발급 |
| `GET` | `/auth/me` | Auth 서버 검증을 거친 현재 사용자 조회 |
| `POST` | `/auth/refresh` | refresh token 회전 및 인증 쿠키 갱신 |
| `POST` | `/auth/logout` | Supabase 세션 종료 및 인증 쿠키 제거 |

로그인 요청:

```json
{"email":"user@example.com","password":"사용자 비밀번호"}
```

회원가입 요청:

```json
{
  "email": "user@example.com",
  "password": "8자 이상 비밀번호",
  "name": "김진우",
  "birth_date": "1990-01-02",
  "sex": "Male"
}
```

이메일 확인이 활성화된 프로젝트는 `email_confirmation_required=true`를 반환하며 확인 후
로그인해야 한다. 비활성화된 프로젝트는 즉시 인증 쿠키를 발급한다.

사용자 응답은 `id`, `email`, `display_name`만 포함한다. 프로필·검진·복약 등 사용자 관련
공개 테이블은 `auth.users.id`와 외래키로 연결하고 RLS에서 `auth.uid()`를 기준으로 접근을
제한해야 한다.

## 대화 세션 API

모든 API는 로그인 세션이 필요하다. Data API에는 서버의 service role key가 아니라
사용자의 access token을 전달하며, `auth.uid()` 기반 RLS로 본인 데이터만 처리한다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/conversations` | 최근 수정 순으로 현재 사용자의 세션 목록 조회 |
| `POST` | `/conversations` | 빈 대화 세션 생성 |
| `GET` | `/conversations/{session_id}` | 세션 요약과 전체 메시지 조회 |
| `DELETE` | `/conversations/{session_id}` | 세션 및 종속 메시지 삭제 |

세션은 `session_id`, `title`, `summary`, `created_at`, `updated_at`을 반환한다. 메시지는
`message_id`, `role`, `content`, `created_at`을 반환한다. 다른 사용자의 세션 ID는 RLS에
의해 조회되지 않으며 API에서는 찾을 수 없음으로 처리한다.

## `GET /health`

Pinecone 연결, namespace별 적재 수, 임베딩 모델, Intent 모델 준비 상태를 반환한다.

```json
{
  "status": "ok",
  "ready": true,
  "vector_backend": "pinecone",
  "indexed_chunks": {
    "disease_info": 54330,
    "health_checkup_info": 30,
    "medication_info": 43330
  },
  "embed_model": "jhgan/ko-sroberta-multitask",
  "intent_classifier": {
    "ready": true,
    "model_version": "intent-v7-41c86ac21d53"
  }
}
```

## `POST /intent/classify`

Intent 분류와 독립적인 Safety Guard 정책을 함께 반환한다. Guard가 작동해도
`source=linear_classifier`이며 Intent와 confidence를 덮어쓰지 않는다.

요청:

```json
{"question":"감기 걸린 것 같은데 어떻게 할까?"}
```

응답 예시:

```json
{
  "intent": "comprehensive",
  "confidence": 0.91,
  "probabilities": {
    "simple_lookup": 0.04,
    "comprehensive": 0.91,
    "general_chat": 0.03,
    "ignore": 0.02
  },
  "uncertain": false,
  "model_version": "intent-v7-41c86ac21d53",
  "source": "linear_classifier",
  "guard_triggered": true,
  "guard_reason": "personal_symptom_guidance",
  "matched_patterns": ["감기 걸린 것 같은데 어떻게"],
  "risk_level": "caution",
  "restricted_actions": ["definitive_diagnosis"],
  "response_policy": "grounded_safe_guidance",
  "emergency": false
}
```

## `POST /chat`

Intent 분류부터 검색·생성까지 실행한 사용자 채팅 결과를 JSON으로 반환한다.
사용자 채팅의 감사 필드는 호환성을 위해 유지하되 `audit_status=not_run`으로 반환한다.

로그인 환경의 멀티턴 요청은 `session_id`만 전달하면 서버가 `chat_messages`의 최근
대화와 `chat_sessions.summary`를 로드한다. 클라이언트의 `history`, `summary`는 Supabase가
설정되지 않은 로컬 호환 모드에서만 사용한다. 의료용어 확인 응답을 이어갈 때는 서버가
반환한 `confirmation_id`와 사용자의 `confirmation_answer`를 전달한다.

```json
{
  "question": "그 약 부작용은?",
  "session_id": "대화 세션 UUID 또는 첫 질문일 때 빈 문자열",
  "history": [
    {"role": "user", "content": "부루펜을 먹었어"},
    {"role": "assistant", "content": "어떤 정보가 궁금하신가요?"}
  ],
  "summary": "",
  "confirmation_id": "",
  "confirmation_answer": null
}
```

질문 처리 단계는 `original_question`(원문), `standalone_question`(대화 문맥 복원),
`resolved_query`(의료용어 정규화 및 실제 임베딩·검색 질문)로 구분한다. 응답에는
`query_rewritten`, `resolved_terms`, `resolution_status`, `conversation_summary`도
포함된다. `resolution_status=CONFIRM` 또는 `AMBIGUOUS`이면 임베딩과 검색을 보류한다.
의료용어 정규화는 직접 PostgreSQL 연결이 없을 때 Supabase의 `medical_term`,
`medical_term_alias`, `medical_term_alias_initial`과 `search_medical_terms_batch` RPC를 사용한다.
검진 용어의 `resolved_terms[].canonical_key`는 `master_checkup_item.item_code`와
동적으로 연결해 개인 검진 결과 조회에 재사용한다. 하나의 별칭이 여러 검사항목을
가리키면 `canonical_keys`에 해당 코드들을 담아 함께 조회하며, 애플리케이션 코드에
검사항목별 별칭·코드 매핑을 따로 두지 않는다.
`수치`, `검진 결과`, `건강 상태`, `이상 수치`처럼 질문의 의미를 보조하는 일반
문맥어 또는 그 조합은 약한 부분·오타 일치만으로 의료용어 확인 후보가 되지 않는다.
`콜레스테롤`처럼 하나의
표현이 여러 `SCREENING` 표준항목에 공통으로 포함되면 모호성 확인 대신 관련
`canonical_keys`를 하나의 검사항목 그룹으로 전달한다.

후속 질문 재작성은 첫 질문에서는 실행하지 않는다. 이전 대화가 있으면 문맥 지시어,
`낮추려면`, `부작용은` 같은 대상 생략 표현을 우선 탐지하고, 명시적 주제가 확인되지
않는 애매한 질문도 재작성 모델이 최종 판단하도록 전달한다. 질문 길이는 재작성 여부의
판정 기준으로 사용하지 않는다.

| Intent | 처리 경로 |
|---|---|
| `simple_lookup` | 일반 질병·검사·의약품 정보용 Pinecone RAG |
| `comprehensive` | 로그인 사용자의 질문 관련 건강검진 RDB 결과와 Pinecone 근거를 결합한 RAG |
| `general_chat` | Pinecone 검색 없이 Gemini 일반 대화 |
| `ignore` | 주식·날씨·스포츠·코딩 등 건강 서비스 외 고정 답변 |

`comprehensive`의 개인 컨텍스트는 사용자 JWT와 RLS로 `users`,
`health_checkup_records`, `health_checkup_results`, `master_checkup_item`을 조회해
구성한다. 기본은 가장 최근 검진 회차의 질문 관련 항목만 사용하고,
`추이`, `변화`, `이전` 등 이력을 요구하는 질문에서만 해당 항목의 과거
회차를 함께 사용한다. DB에 저장된 측정값·단위·`status`는 재판정하지
않고 그대로 최종 프롬프트에 전달하며, 개인 컨텍스트는 캐시하지 않는다.
분류 모델이 `simple_lookup`으로 판정해도 "내", "나의", "제" 등 본인 표현이
있고 실제 질문 관련 검진값이 조회되면 `comprehensive`로 승격한다. 이 경우
`intent_source=personal_health_context_override`를 반환한다.

RAG의 기본 검색 결과 검사는 다음을 구분한다.

| `retrieval_assessment.status` | 의미 |
|---|---|
| `no_evidence` | 최소 유사도 기준을 통과한 청크가 없음 |
| `entity_mismatch` | 질문의 명시 의약품·질병명과 청크 대상이 일치하지 않음 |
| `evidence_available` | 생성 가능한 청크와 대상 일치를 확인함 |
| `personal_evidence_available` | VDB 청크는 부족하지만 인증된 개인 검진 RDB 근거가 있어 해당 사실 범위에서 생성 가능 |

`comprehensive`에서 개인 검진 컨텍스트가 확보되면 `no_evidence` 또는
`entity_mismatch`만으로 생성을 중단하지 않는다. 이 경우 개인 측정값·측정일·단위·DB
상태는 답할 수 있지만, VDB가 뒷받침하지 않는 일반 기준·원인·진단은 추측하지 않는다.

개발자용 RAG 서비스 사후 감사의 `evidence_status`는 `sufficient`, `partial`, `insufficient`, `unknown` 중
하나이다. 복합 질문에서 일부 항목만 근거가 있으면 `partial`로 기록하고, 근거가 있는
항목은 답하면서 `unanswered_items`에 근거 부족 항목을 남긴다.

응답 예시:

```json
{
  "question": "판콜에스내복액이 무슨 약이고 부작용은 뭐야?",
  "session_id": "대화 세션 UUID",
  "intent": "simple_lookup",
  "confidence": 0.93,
  "probabilities": {},
  "uncertain": false,
  "model_version": "intent-v7-41c86ac21d53",
  "intent_source": "linear_classifier",
  "guard_triggered": false,
  "guard_reason": null,
  "matched_patterns": [],
  "risk_level": "normal",
  "restricted_actions": [],
  "response_policy": "standard_grounded",
  "emergency": false,
  "answer": "판콜에스내복액의 효능은 ... 현재 검색 자료에서는 부작용 항목이 확인되지 않았습니다.",
  "sources": ["식품의약품안전처 의약품개요정보(e약은요) OpenAPI"],
  "grounded": true,
  "chunks": [],
  "citations": [],
  "verification_method": "retrieval_check",
  "verification_reason": "intent:simple_lookup",
  "grounding_errors": [],
  "unsupported_claims": [],
  "evidence_status": "evidence_available",
  "retrieval_assessment": {
    "status": "evidence_available",
    "eligible": true,
    "reason": "최소 검색 기준을 통과한 청크가 있으며 명시 대상 불일치가 없습니다.",
    "max_score": 0.91,
    "query_entities": ["판콜에스내복액"],
    "matched_entities": ["판콜에스내복액"]
  },
  "audit_status": "not_run",
  "audit_summary": "",
  "unanswered_items": [],
  "safety_violations": [],
  "searched_collections": ["disease_info", "health_checkup_info", "medication_info"],
  "failed_collections": [],
  "personal_context_used": false
}
```

## `POST /chat/stream`

`POST /chat`과 같은 흐름을 `text/event-stream`으로 제공한다.

`emergency`는 스트리밍과 RAG를 중단하는 값이 아니다. 긴급 행동 안내를 답변 앞에
배치하고, 검색 청크에서 확인되는 사용자의 요청 정보도 이어서 제공한다.

| 이벤트 | 데이터 | 설명 |
|---|---|---|
| `progress` | `{"stage":"단계 코드","message":"고정 안내 문구"}` | 실제 백엔드 처리 단계 진입 알림. LLM이 문구를 생성하지 않는다. |
| `token` | `{"text":"생성 문자열"}` | 최종 답변 조각 |
| `complete` | `ChatResponse` | 답변과 검색·안전·감사 메타데이터 |
| `error` | `{"message":"안내 문구"}` | 스트리밍 중 오류 |

`progress.stage`는 실제 실행 경로에 따라 `load_conversation`, `prepare_query`,
`classify_intent`, `load_health_context`, `search_evidence`, `generate_answer`, `answer_stream_complete`,
`summarize_conversation`, `save_conversation` 중 필요한 단계만 순서대로 전달한다.
`answer_stream_complete`는 사용자에게 표시할 답변 토큰 생성이 끝났음을 알리며 안내 문구를
포함하지 않는다. 프런트엔드는 남은 토큰 표시를 마치면 진행 문구를 제거한다.
사용자용 `POST /chat`, `POST /chat/stream`은 답변 본문을 변경하지 않는 사후 감사 LLM
호출을 생략한다. 개발자용 RAG 서비스의 감사 옵션은 기본 활성화 상태를 유지한다.

내부 근거 연결용 `[C1]` 라벨은 서버 스트림 필터가 사용자 답변에서 제거한다. 원본
응답의 인용 기록은 라벨을 이용해 실제 `citations`를 청크에 연결한다.

## 검색·답변 점검 API

- `POST /search`: 지정 namespace 검색만 수행한다.
- `POST /ask`: 지정 namespace를 사용한 기존 단일 RAG API다.
- `POST /search/combined`: 설정된 모든 namespace를 병렬 검색하고 병합한다.
- `POST /ask/combined`: 병합 청크를 기본 검사한 뒤 생성·감사를 수행한다.

다중 검색 기본 설정:

```text
SEARCH_COLLECTIONS=health_checkup_info,disease_info,medication_info
SEARCH_TOP_K_PER_COLLECTION=10
SEARCH_FINAL_TOP_K=6
SEARCH_MAX_PER_COLLECTION=6
SEARCH_MIN_SCORE=0.0
```

현재 애플리케이션은 namespace별 후보 10개를 모아 전체 정렬한 뒤 최종 6개를 선택한다.

## 오류

| 상태 | 조건 |
|---|---|
| `400` | 등록되지 않은 collection |
| `422` | 요청 필드 누락 또는 형식 오류 |
| `503` | Intent 모델 artifact 없음 또는 모든 namespace 검색 실패 |
| `500` | Pinecone, 임베딩 모델 또는 Gemini 호출 오류 |

## collection과 namespace

| API collection | Pinecone namespace |
|---|---|
| `disease_info` | `disease_info` |
| `health_checkup_info` | `health_checkup_info` |
| `medication_info` | `medication_info` |
