# Heapy AI health care 파이프라인 — 노드별 입출력 명세

팀 분업 개발용. 각 노드는 공유 State 객체를 받아 **입력 필드**를 읽고 **출력 필드**를 채운 뒤 다음 노드로 넘긴다. 자신이 맡은 노드의 입력/출력만 맞추면 된다.

- 노드 간 전달: 메모리상 State 객체 참조 (직렬화 없음)
- 직렬화(JSON/바이너리)는 경계에서만: 클라이언트 응답, vLLM 호출, Redis 저장

---

## 공유 State 필드

| 필드 | 타입 | 채우는 노드 |
|---|---|---|
| `session_id` | str | S1 |
| `is_new_session` | bool | S1CHK |
| `raw_query` | str | 입력 |
| `resolved_query` | str | S3 / S4 |
| `history` | Turn[] | S2 / S4 |
| `summary` | str \| null | S2 |
| `query_embedding` | float[] | A1 |
| `intent` | enum | A4 |
| `guard_triggered` | bool | SG |
| `guard_reason` | str | null | SG |
| `sub_intents` | str[] | B1 |
| `chunks` | Chunk[] \| null | 검색/캐시 |
| `cache_hit` | bool | SC1 / BC1 |
| `user_context` | object \| null | D2 |
| `prompt` | str | C2 / B4 / C5 |
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
| S1 세션 조회 | `raw_query` | `session_id` |
| S1CHK 세션 존재 여부 | `session_id` | `is_new_session` |
| S2 컨텍스트 로드 | `session_id` | `history`, `summary` |
| S3 질문 재구성 | `raw_query`, `history`, `summary` | `resolved_query` |
| S4 신규 세션 초기화 | `raw_query` | `resolved_query`(=원문), `history`(=[]) |

### 의도 분류

| 노드 | 입력 | 출력 |
|---|---|---|
| SG Safety Guard | `resolved_query` | `guard_triggered`, `guard_reason`, 차단 시 `intent=ignore` |
| A1 임베딩 변환 | `resolved_query` | `query_embedding` |
| A2~A3 분류기 | `query_embedding` | (내부 로짓/확률) |
| A4 Intent 분류 | (확률) | `intent` |

### 검색 (simple/comprehensive 공통)

| 노드 | 입력 | 출력 |
|---|---|---|
| B1 Sub-intent 분류 | `resolved_query`, `intent` | `sub_intents` |
| SC1 / BC1 캐시 조회 | `query_embedding` | `cache_hit`, (히트 시) `chunks` |
| C1 / B2 VDB 검색 | `query_embedding`, `sub_intents` | `chunks` |
| VCHK 응답 성공 여부 | `chunks` | `error` (실패 시) |
| C1CHK / B3CHK 결과 유무 | `chunks` | (분기만) |
| SC3 / BC3 캐시 저장 | `query_embedding`, `chunks` | (Redis 기록) |

### 개인 컨텍스트 (comprehensive 전용, 캐시 안 함)

| 노드 | 입력 | 출력 |
|---|---|---|
| AU1 접근권한 확인 | `session_id` | (분기만) |
| D1 프로필 조회 | `session_id` | (원시 프로필) |
| D2 데이터 조합 | (원시 프로필) | `user_context` |

### 프롬프트 · LLM

| 노드 | 입력 | 출력 |
|---|---|---|
| C2 프롬프트 (simple) | `chunks`, `history` | `prompt` |
| B4 프롬프트 (comprehensive) | `chunks`, `user_context`, `history`, `summary` | `prompt` |
| C5 프롬프트 (chat) | `history`, `summary` | `prompt` |
| L1 LLM 호출 | `prompt` | (스트림 시작) |
| L2 / L3 스트림 전송 | (LLM 토큰) | (클라이언트로 청크 전송) |
| B5 응답 검증 | (누적 응답) | (검증된 응답) |

---

## 주의 사항 (분업 시 합의 필요)

1. **`query_embedding`은 A1에서 한 번 생성 후 재사용** — 캐시 조회(SC1/BC1) → 검색(C1/B2) → 캐시 저장(SC3/BC3)에서 같은 값을 쓴다. 각자 다시 임베딩하지 말 것.
2. **`chunks` = null vs []** 구분을 지킬 것 — 검색 담당은 인프라 실패 시 null, 결과 없음 시 [] 를 반환해야 VCHK/결과유무 분기가 동작한다.
3. **개인 컨텍스트(D1/D2)는 캐시 금지** — 사용자·시점마다 달라지므로 QCACHE에 넣지 않는다. VDB 청크만 캐시한다.
4. **요약(summary)은 O3가 생성, S2가 로드** — S2는 직전 턴의 O3가 만들어 둔 요약을 읽기만 한다. S2에서 요약을 새로 만들지 않는다.
