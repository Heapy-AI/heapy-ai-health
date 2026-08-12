# Heapy AI health care 파이프라인 — 노드별 입출력 명세

팀 분업 개발용. 각 노드는 공유 State 객체를 받아 **입력 필드**를 읽고 **출력 필드**를 채운 뒤 다음 노드로 넘긴다. 자신이 맡은 노드의 입력/출력만 맞추면 된다.

- 노드 간 전달: 메모리상 State 객체 참조 (직렬화 없음)
- 직렬화(JSON/바이너리)는 경계에서만: 클라이언트 응답, vLLM 호출, Supabase 저장

---

## 공유 State 필드

| 필드 | 타입 | 채우는 노드 |
|---|---|---|
| `session_id` | str | S1 |
| `is_new_session` | bool | S1CHK |
| `raw_query` | str | 입력 |
| `standalone_question` | str | S3 / S4 |
| `is_follow_up` | bool | S3 |
| `current_topic` | str | S3 |
| `inherited_target` | str | S3 |
| `personal_context_required` | bool | S3 |
| `resolved_query` | str | QN |
| `resolution_status` | str | QN |
| `history` | Turn[] | S2 / S4 |
| `summary` | str \| null | S2 |
| `query_embedding` | float[] | A1 |
| `intent` | enum | A4 |
| `guard_triggered` | bool | SG |
| `guard_reason` | str | null | SG |
| `search_collections` | str[] | B1 |
| `chunks` | Chunk[] \| null | 검색/캐시 |
| `cache_hit` | bool | SC1 / BC1 |
| `user_context` | object \| null | D2 |
| `prompt` | str | C2 / B4 / C5 |
| `retrieval_assessment` | object \| null | RCHK |
| `evidence_status` | str | APOST |
| `audit_status` | str | APOST |
| `audit_summary` | str | APOST |
| `error` | str \| null | ERRMSG |

**`chunks` 3가지 상태 (중요):**
- `null` = 검색 인프라 실패 (VDB 타임아웃 등) → 에러
- `[]` = 검색 성공했으나 결과 0건 → 일반 대화 전환
- `[...]` = 정상 → 프롬프트 구성으로

**서브 타입:**
- `Chunk` = { text: str, doc_type: enum, score: float, source_id: str }
  - doc_type: catalog / policy / example / experience / glossary / feedback
- `Turn` = { role: "user"|"assistant", content: str, timestamp: datetime }

---

## 노드별 입출력

### 세션·컨텍스트

| 노드 | 입력 | 출력 |
|---|---|---|
| S1 세션 조회 | 로그인 사용자, `session_id` | `session_id` |
| S1CHK 세션 존재 여부 | `session_id` | `is_new_session` |
| S2 컨텍스트 로드 | `session_id` | Supabase의 최근 `history`, `summary` |
| S3 문맥 판단·질문 재구성 | `raw_query`, `history`, `summary` | `standalone_question`, `is_follow_up`, `current_topic`, `inherited_target`, `personal_context_required` (첫 질문 외 항상 구조화 LLM 호출) |
| S4 신규 세션 초기화 | `raw_query` | `standalone_question`(=원문), `history`(=[]) |
| QN 의료용어 정규화 | `standalone_question` | `resolved_query`, `resolution_status`, `resolved_terms[].canonical_key`, `resolved_terms[].canonical_keys` |

### 의도 분류

| 노드 | 입력 | 출력 |
|---|---|---|
| SG Safety Guard | `resolved_query` | `guard_triggered`, `guard_reason`, `risk_level`, `restricted_actions`, `response_policy`, `emergency` (위험 증상 + 개인·현재 상황 + 요청 행동 + 정보형 의문문 조합 판정) |
| A1 임베딩 변환 | `resolved_query` | `query_embedding` |
| A2~A3 분류기 | `query_embedding` | (내부 로짓/확률) |
| A4 Intent 분류 | (확률) | `intent` |

### 검색 (simple/comprehensive 공통)

| 노드 | 입력 | 출력 |
|---|---|---|
| B1 검색 namespace 설정 | `intent` | `search_collections` |
| SC1 / BC1 캐시 조회 | `query_embedding` | `cache_hit`, (히트 시) `chunks` |
| C1 / B2 VDB 검색 | `query_embedding`, `search_collections` | `chunks` |
| VCHK 응답 성공 여부 | `chunks` | `error` (실패 시) |
| C1CHK / B3CHK 결과 유무 | `chunks` | (분기만) |
| SC3 / BC3 캐시 저장 | `query_embedding`, `chunks` | (Redis 기록) |

### 개인 컨텍스트 (comprehensive 전용, 캐시 안 함)

| 노드 | 입력 | 출력 |
|---|---|---|
| AU1 접근권한 확인 | 사용자 JWT | `auth.uid()`로 본인 여부를 검증하는 RLS 분기 |
| D1 프로필·검진 조회 | `auth.uid()`, `standalone_question`, QN의 표준 검사항목 코드 | `users`, `health_checkup_records`, 질문 관련 `health_checkup_results`, `master_checkup_item` |
| D2 데이터 조합 | 프로필, 검진 회차, 검진 결과 | 측정일·항목·값·단위·저장 `status`를 포함한 `user_context` |

D1은 일반적인 검사항목 질문이면 최근 회차의 해당 항목만 조회하고,
추이·변화 질문에서만 과거 회차까지 조회한다. 개인 컨텍스트는 캐시하지 않으며
`simple_lookup`, `general_chat`, `ignore`에서는 D1/D2를 실행하지 않는다.
검사항목 선택은 QN이 Supabase 용어집에서 반환한 `canonical_key` 또는
`canonical_keys`를 `master_checkup_item.item_code`와 연결하며, 특정 검사항목을
애플리케이션 코드에 별도 매핑하지 않는다.

### 프롬프트 · LLM

| 노드 | 입력 | 출력 |
|---|---|---|
| C2 프롬프트 (simple) | `chunks`, `history` | `prompt` |
| B4 프롬프트 (comprehensive) | `chunks`, `user_context`, `raw_query`, 제한된 `history` | `prompt` |
| C5 프롬프트 (chat) | `history`, `summary` | `prompt` |
| RCHK 검색 결과 기본 검사 | `chunks`, `user_context`, 질문 | `retrieval_assessment`, `grounded` (VDB가 부족해도 인증된 개인 검진 근거가 있으면 제한 생성 허용) |
| L1 최종 답변 호출 | 질문, `chunks`, `user_context`, 안전 정책 | 요청 범위 안의 근거만 사용한 최단 완전 답변 스트림 |
| L2 / L3 스트림 전송 | 최종 답변 토큰 | (클라이언트로 전송) |
| APOST 사후 감사 | 최종 답변, `chunks`, 안전 정책 | `audit_status`, `audit_summary`, `evidence_status`, `unanswered_items`, `unsupported_claims`, `safety_violations` |

---

## 주의 사항 (분업 시 합의 필요)

1. **`query_embedding`은 A1에서 한 번 생성 후 재사용** — 캐시 조회(SC1/BC1) → 검색(C1/B2) → 캐시 저장(SC3/BC3)에서 같은 값을 쓴다. 각자 다시 임베딩하지 말 것.
2. **`chunks` = null vs []** 구분을 지킬 것 — 검색 담당은 인프라 실패 시 null, 결과 없음 시 [] 를 반환해야 VCHK/결과유무 분기가 동작한다.
3. **개인 컨텍스트(D1/D2)는 캐시 금지** — 사용자·시점마다 달라지므로 QCACHE에 넣지 않는다. VDB 청크만 캐시한다.
4. **요약(summary)은 O3가 생성, S2가 로드** — S2는 직전 턴의 O3가 만들어 둔 요약을 읽기만 한다. S2에서 요약을 새로 만들지 않는다.
5. **대화 저장은 사용자 JWT와 RLS 사용** — service role key로 소유권 검사를 우회하지 않으며, 메시지 두 건과 요약은 `append_chat_turn` RPC 한 트랜잭션으로 저장한다.
