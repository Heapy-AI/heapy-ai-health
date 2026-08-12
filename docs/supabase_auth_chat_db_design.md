# Supabase 인증·대화 DB 설계

- 작성자: 김진우
- 적용 마이그레이션: `database/migrations/002_supabase_auth_chat.sql`, `database/migrations/003_supabase_medical_term_search.sql`, `database/migrations/004_health_checkup_rls.sql`, `database/migrations/005_health_checkup_item_index.sql`

## 목적

Supabase Auth 계정과 HEAPY 프로필을 같은 UUID로 연결하고, 로그인 사용자별 챗봇
세션·메시지·대화 요약을 PostgreSQL에 보존한다. 애플리케이션은 publishable key와
사용자의 access token만 사용하며 service role key는 사용하지 않는다.

## 테이블 관계

```text
auth.users.id
  └─ public.users.user_id
       ├─ public.chat_sessions.user_id
       │    └─ public.chat_messages.session_id
       └─ public.health_checkup_records.user_id
            └─ public.health_checkup_results.record_id
```

- `auth.users`: Supabase가 관리하는 이메일·비밀번호, 세션, 인증 식별자 저장소
- `public.users`: 이름, 생년월일, 성별을 보관하는 애플리케이션 프로필
- `public.chat_sessions`: 사용자별 대화 제목, 누적 요약, 생성·수정 시각
- `public.chat_messages`: 세션별 `user`·`assistant` 원문과 저장 순서
- `public.health_checkup_records`: 사용자별 검진 회차와 측정일
- `public.health_checkup_results`: 검진 회차별 항목 측정값과 저장된 판정 상태
- `public.master_checkup_item`: 검사항목 코드·이름·표준 단위 마스터

## 기존 사용자 보존

기존 `public.users` 행은 삭제하거나 수정하지 않는다. `auth.users` 외래키는 `NOT VALID`로
추가해 기존 불일치 행을 보존하면서, 마이그레이션 이후 생성·수정되는 프로필에는 동일
UUID 규칙을 강제한다. 기존 데이터를 Auth 계정에 연결하는 작업은 별도 데이터 이관으로
분리한다.

## 회원가입

`POST /auth/signup`이 이름·생년월일·성별을 Auth 메타데이터로 전달한다. `auth.users`
행이 생성되면 `private.handle_new_auth_user` 트리거가 같은 UUID로 `public.users` 프로필을
생성한다. 비밀번호나 인증 토큰은 `public.users`에 저장하지 않는다.

## 대화 저장

첫 질문은 빈 `chat_sessions`를 만들고 생성된 `session_id`를 응답한다. 다음 질문부터는
해당 세션의 최신 메시지와 요약을 서버가 로드한다. 답변 완료 시 `append_chat_turn` RPC가
다음을 한 트랜잭션으로 수행한다.

1. 세션 소유권을 `auth.uid()`로 확인한다.
2. 세션 제목·요약·수정 시각을 갱신한다.
3. 사용자 메시지와 어시스턴트 메시지를 순서대로 저장한다.

첫 질문은 문맥 판단 LLM을 생략한다. 두 번째 질문부터는 `chat_messages`의 제한된 최근
대화와 `chat_sessions.summary`를 구조화 문맥 판단에 함께 사용한다. 최종 답변 생성에는
원문 질문과 제한된 최근 대화도 전달하되, 이 대화 데이터는 의료 사실의 근거가 아니므로
개인 검진 RDB 또는 VDB 검색 근거를 대신하지 않는다.

의료용어 확인이 필요한 `CONFIRM`, `AMBIGUOUS` 등 중간 응답은 확정 대화 턴으로 저장하지
않는다.

## 접근 제어

- `public.users`: 본인 프로필 조회·수정만 허용
- `public.chat_sessions`: 본인 세션 조회·생성·수정·삭제만 허용
- `public.chat_messages`: 본인 세션의 메시지 조회·생성만 허용
- `public.health_checkup_records`: `auth.uid() = user_id`인 본인 회차 조회만 허용
- `public.health_checkup_results`: 본인 소유 검진 회차에 속한 결과 조회만 허용
- `public.master_checkup_item`: 인증된 사용자에게 읽기만 허용
- 익명 역할에는 사용자·대화·검진 테이블과 저장 RPC 권한을 부여하지 않음

RLS 정책과 애플리케이션의 서버 측 세션 검증을 함께 적용한다. 브라우저에는 access token과
refresh token을 JavaScript에서 읽을 수 없는 `HttpOnly`, `SameSite=Lax` 쿠키로 보관한다.

## 조회 성능

- 세션 상세와 메시지는 서로 의존하지 않으므로 동시에 조회한다.
- 연속 UI 요청의 Auth 사용자 검증 결과는 원본 토큰 대신 토큰 해시를 키로 30초만
  메모리에 유지하고, 로그아웃 시 즉시 제거한다.
- 세션 선택 상태와 답변 완료 후 세션 제목·수정 시각은 화면에 먼저 반영하고, 이후
  Supabase 목록을 다시 조회해 최종 데이터와 맞춘다.
- 각 Data API 요청에는 계속 사용자 access token을 전달하므로 조회 최적화 이후에도
  `auth.uid()` 기반 RLS 소유권 검사는 유지된다.

## 의료용어 정규화

공개 사전인 `medical_term`, `medical_term_alias`, `medical_term_alias_initial`은 활성 행의
읽기만 `anon`, `authenticated` 역할에 허용한다. 쓰기 권한은 부여하지 않는다. 백엔드는
후보마다 HTTP 요청을 반복하지 않고 `search_medical_terms_batch` RPC 한 번으로 질문의
의료용어 후보를 조회한다.

## 개인 건강검진 컨텍스트

`comprehensive` 질문에서만 사용자 JWT를 Supabase Data API에 전달해 본인
검진 데이터를 조회한다. 질문에 검사항목이 명시되면 해당 `item_code`만,
전체 검진·이상 항목을 물으면 해당 범위만 조회한다. 기본은 최신 회차이며
추이 질문은 과거 회차를 함께 가져온다. 측정값·단위·`status`는 DB 값을
그대로 프롬프트에 넣고, Pinecone에서 검색한 공용 의학 근거와 결합한다.
개인 검진 컨텍스트는 응답 캐시에 저장하지 않는다.
