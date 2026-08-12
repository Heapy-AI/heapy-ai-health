# Healpy AI health care 파이프라인 — 내부 State 설계 문서
Healpy AI health care의 요청 처리 파이프라인에서 노드 간에 흐르는 내부 State 객체의 설계를 정의한다. 이 문서는 프로세스 내부 데이터 모델을 다루며, 외부로 노출되는 API 계약(요청/응답 JSON)은 별도의 API 명세서에서 다룬다.

## 설계 원칙

파이프라인은 단일 State 객체를 노드에서 노드로 흘려보내는 방식으로 동작한다. 각 노드는 State를 입력으로 받아 자신이 담당하는 필드만 채우거나 갱신한 뒤 다음 노드로 넘긴다. 노드 간 전달은 직렬화 없이 메모리상 객체 참조로 이루어지며, 직렬화(JSON, 바이너리 등)는 프로세스·서비스 경계를 넘을 때(클라이언트 응답, vLLM 호출, Supabase 저장)에만 발생한다.

이 방식을 택한 이유는 다음과 같다. 첫째, intent에 따른 분기(simple / comprehensive / general_chat / ignore)가 많아 노드마다 독립적인 시그니처를 두면 관리 비용이 커진다. 둘째, comprehensive 경로는 VDB 검색과 RDB 조회를 병렬로 수행한 뒤 하나의 프롬프트로 합류시켜야 하는데, 단일 State에 양쪽 결과를 담으면 합류가 자연스럽다. 셋째, 멀티턴 컨텍스트(세션 ID, 히스토리, 요약)가 거의 모든 노드에서 필요하므로 State에 담아두는 편이 인자 전달보다 간결하다. 넷째, 로깅·모니터링 노드가 State의 특정 필드만 읽으면 되어 관측성이 좋다.

## State 스키마

파이프라인 전 구간에서 공유되는 State의 필드 정의다. 각 필드는 특정 노드에서 최초로 채워지며, 이후 노드는 이를 읽거나 갱신한다.

| 필드 | 타입 | 최초 기록 노드 | 설명 |
|---|---|---|---|
| `session_id` | 문자열 | S1 | 세션 식별자 |
| `is_new_session` | 불리언 | S1CHK | 콜드 스타트(신규 세션) 여부 |
| `raw_query` | 문자열 | U (입력) | 사용자 원문 질문 |
| `history` | 턴 목록 | S2 | 최근 N턴의 대화 기록 (신규 세션은 빈 목록) |
| `summary` | 문자열 또는 없음 | S2 | 이전 턴들의 압축 요약본 (신규 세션은 없음) |
| `standalone_question` | 문자열 | S3 또는 S4 | 대명사·생략을 복원한 독립형 질문. 신규 세션은 원문과 동일 |
| `is_follow_up` | 불리언 | S3 | 이전 대화에서 이어지는 후속 질문인지에 대한 LLM 판단 |
| `current_topic` | 문자열 | S3 | 현재 질문의 핵심 주제 |
| `inherited_target` | 문자열 | S3 | 이전 대화에서 이어받은 검사·질환·약·검진 결과 등의 대상 |
| `personal_context_required` | 불리언 | S3 | 개인 건강검진 RDB 조회 필요 여부에 대한 LLM 판단 |
| `resolved_query` | 문자열 | QN | 의료용어를 정규화한 실제 분류·검색 질문 |
| `resolution_status` | 문자열 | QN | NO_MATCH / RESOLVED / CONFIRM / AMBIGUOUS |
| `query_embedding` | 실수 배열 | A1 | 질문 임베딩 벡터. 캐시 조회·검색·저장에서 재사용 |
| `intent` | 열거형 | A4 | simple_lookup / comprehensive / general_chat / ignore |
| `guard_triggered` | 불리언 | SG | 의료 Safety Guard 작동 여부 |
| `guard_reason` | 문자열 또는 없음 | SG | definitive_diagnosis / medication_decision / medical_visit_decision |
| `risk_level` | 문자열 | SG | normal / caution / emergency |
| `restricted_actions` | 문자열 목록 | SG | 최종 답변에서 금지할 의료적 결정 |
| `response_policy` | 문자열 | SG | 일반·주의·긴급 응답 정책 |
| `search_collections` | 문자열 목록 | B1 | 설정으로 고정한 병렬 검색 대상 namespace |
| `chunks` | 청크 목록 또는 없음 | 검색/캐시 노드 | 검색 결과 청크. 아래 "chunks 상태 규약" 참조 |
| `cache_hit` | 불리언 | SC1 또는 BC1 | 캐시 히트 여부 |
| `user_context` | 객체 또는 없음 | D2 | RDB에서 조합한 개인 컨텍스트 (comprehensive 경로만) |
| `prompt` | 문자열 | C2 / B4 / C5 | LLM에 전달할 최종 프롬프트 |
| `retrieval_assessment` | 객체 또는 없음 | RCHK | 검색 결과 존재·최소 기준·명시 대상 일치 검사 |
| `evidence_status` | 문자열 | APOST | sufficient / partial / insufficient / unknown |
| `audit_status` | 문자열 | APOST | passed / failed / error / not_run |
| `audit_summary` | 문자열 | APOST | 사용자 본문을 바꾸지 않는 사후 감사 요약 |
| `error` | 문자열 또는 없음 | ERRMSG | 에러 발생 시 안내 메시지. 정상 흐름에서는 없음 |

### chunks 상태 규약

`chunks` 필드는 검색의 두 가지 실패 유형을 구분하기 위해 세 가지 상태를 가진다. 이 구분은 다이어그램의 응답 성공 여부(VCHK)와 검색결과 유무(C1CHK / B3CHK) 두 단계가 서로 다른 관심사임을 반영한다.

`없음(None)`은 검색이 인프라 레벨에서 실패했음을 의미한다. VDB 호출 자체가 타임아웃되거나 재시도를 초과한 경우로, VCHK에서 에러 처리로 분기한다. `빈 목록([])`은 호출은 성공했으나 매칭되는 청크가 하나도 없음을 의미한다. 이 경우 C1CHK / B3CHK에서 일반 대화(general_chat)로 전환한다. `비어 있지 않은 목록`은 정상적으로 청크를 확보한 상태로, 프롬프트 구성 단계로 진행한다.

## 서브 타입

State의 복합 필드에서 반복적으로 사용되는 구조를 정의한다.

### Chunk

VDB 검색으로 확보한 개별 지식 청크를 표현한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `text` | 문자열 | 청크 본문 |
| `doc_type` | 열거형 | catalog / policy / example / experience / glossary / feedback |
| `score` | 실수 | 쿼리와의 유사도 점수 |
| `source_id` | 문자열 | 원본 문서 식별자 |

### Turn

멀티턴 히스토리의 개별 대화 턴을 표현한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `role` | 열거형 | user / assistant |
| `content` | 문자열 | 발화 내용 |
| `timestamp` | 시각 | 발화 시각 |

## 노드별 입출력 (핵심 경로)

분류에서 검색을 거쳐 LLM 응답에 이르는 핵심 경로의 노드별 입출력을 정의한다. "입력"은 해당 노드가 State에서 읽는 필드, "출력"은 채우거나 갱신하는 필드다. 인증·컨텍스트 수집(AUTH / COLLECT)은 comprehensive 경로에서만 실행된다.

### 세션·컨텍스트 관리

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| S1 세션 조회 | 로그인 사용자, `session_id` | `session_id` | Supabase에서 본인 세션 조회. 없으면 새 세션 생성 |
| S1CHK 세션 존재 여부 | `session_id` | `is_new_session` | 기존/신규 분기 |
| S2 컨텍스트 로드 | `session_id` | `history`, `summary` | `chat_messages` 최근 기록과 `chat_sessions.summary` 로드 |
| S3 문맥 판단·질문 재구성 | `raw_query`, `history`, `summary` | `standalone_question`, `is_follow_up`, `current_topic`, `inherited_target`, `personal_context_required` | 첫 질문을 제외한 모든 질문에서 구조화 LLM 호출 |
| S4 신규 세션 초기화 | `raw_query` | `standalone_question`, `history`(빈 목록) | 재구성 스킵, 원문 그대로 |
| QN 의료용어 정규화 | `standalone_question` | `resolved_query`, `resolution_status` | 확인·모호 상태면 검색 보류 |

### 의도 분류 (Decider)

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| SG Safety Guard | `resolved_query` | `guard_triggered`, `guard_reason`, `risk_level`, `restricted_actions`, `response_policy` | 위험 증상·개인/현재 상황·요청 행동·정보형 의문문을 조합해 판단하며 Intent와 RAG 진행 여부는 변경하지 않음 |
| A1 임베딩 변환 | `resolved_query` | `query_embedding` | Sentence-Transformers. 이후 캐시·검색에서 재사용 |
| A2 Linear Layer | `query_embedding` | (로짓, 내부) | 학습된 선형 분류기 |
| A3 Softmax | (로짓) | (확률 분포, 내부) | intent별 확률 |
| A4 Intent 분류 | (확률 분포) | `intent` | argmax + 임계값 |

### 검색 (Simple / Comprehensive 공통 패턴)

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| B1 검색 namespace 설정 | `intent` | `search_collections` | Sub-intent 분류 없이 설정된 전체 검색 대상 사용 |
| SC1 / BC1 캐시 조회 | `query_embedding` | `cache_hit`, (히트 시)`chunks` | 유사도 ≥ 임계값이면 히트 |
| C1 / B2 VDB 검색 | `query_embedding`, `search_collections` | `chunks` | 캐시 미스 시 namespace 병렬 검색·병합 |
| VCHK 응답 성공 여부 | `chunks` | `error`(실패 시) | 없음이면 인프라 실패 → 에러 분기 |
| C1CHK / B3CHK 검색결과 유무 | `chunks` | (분기만) | 빈 목록이면 general_chat 전환 |
| SC3 / BC3 캐시 저장 | `query_embedding`, `chunks` | (QCACHE 기록) | TTL과 함께 저장 |

### 개인 컨텍스트 (Comprehensive 전용, 캐시 제외)

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| AU1 접근권한 확인 | `session_id` | (분기만) | 인증 성공/실패 분기 |
| D1 프로필 조회 | `session_id` | (원시 프로필, 내부) | RDB 조회. 캐시 대상 아님 |
| D2 데이터 조합 | (원시 프로필) | `user_context` | 검진·복약·생활 데이터 조합 |

### 프롬프트 구성 및 LLM

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| C2 프롬프트 구성 (simple) | `chunks`, `history` | `prompt` | 짧은 프롬프트 |
| B4 프롬프트 구성 (comprehensive) | `chunks`, `user_context`, `raw_query`, 제한된 `history` | `prompt` | 의료 사실은 검색·개인 근거로 제한하고 원문·최근 대화는 문맥 이해에만 사용 |
| C5 프롬프트 구성 (chat) | `history`, `summary` | `prompt` | 자유 대화 |
| L1 LLM 호출 | `prompt` | (스트림 시작) | 스트리밍 모드 |
| L2 / L3 스트림 전송 | (LLM 토큰) | (출력으로 청크 전송) | 토큰 단위 전송 |
| RCHK 검색 결과 기본 검사 | 질문, `chunks` | `retrieval_assessment`, `grounded` | 결과 존재·최소 기준·명시 대상 일치를 코드로 검사 |
| L1 최종 답변 생성 | 질문, `chunks`, `user_context`, 안전 정책 | (스트림 시작) | 질문의 요청 범위를 먼저 판단하고 직접 필요한 근거만 사용해 가장 짧은 완전한 답변 생성 |
| APOST 사후 감사 | 최종 답변, `chunks`, 안전 정책 | `audit_status`, `audit_summary`, `evidence_status`, `unanswered_items`, `unsupported_claims`, `safety_violations` | 본문을 교체하지 않고 근거·안전 정책 준수 여부 기록 |

## State 라이프사이클

하나의 요청이 처리되는 동안 State가 채워지는 순서를 요약한다.

요청이 들어오면 S1이 세션을 조회하고 S1CHK가 신규 여부를 판정한다. 기존 세션이면 S2가 히스토리와 요약을 로드하고 S3가 규칙 선별 없이 구조화된 문맥 판단과 질문 재구성을 수행하며, 신규 세션이면 S4가 빈 히스토리로 초기화하고 원문을 그대로 사용한다. A1과 A4가 Intent v7을 분류하고, SG는 별도로 위험 수준과 금지 행동을 기록한다. Guard는 Intent나 검색 경로를 변경하지 않는다.

intent가 simple 또는 comprehensive이면 먼저 캐시를 조회하고, 히트하면 저장된 청크를 재사용하며 미스이면 VDB를 검색한다. VDB 응답 성공을 확인한 뒤 검색 결과 유무를 판정하고, 결과가 있으면 캐시에 저장한 다음 프롬프트를 구성한다. comprehensive 경로는 이와 병렬로 인증을 거쳐 개인 컨텍스트를 조합하며, 이 개인 데이터는 캐시하지 않는다.

검색 문맥이 완성되면 RCHK가 검색 결과 존재, 설정된 최소 유사도 통과, 질문의 명시 대상과 청크 대상 일치를 확인한다. 통과하면 L1이 근거가 있는 질문 항목은 답하고 부족한 항목은 확인되지 않았다고 구분해 스트리밍한다. `emergency`여도 이 흐름은 중단하지 않고 긴급 행동 안내를 먼저 배치한 뒤 요청 정보까지 제공한다. 누적이 끝나면 APOST가 근거 충족도와 안전 정책 준수 여부를 감사하되 사용자에게 이미 표시한 본문은 바꾸지 않는다. 분류 결과, 안전 정책, 검색 검사, 감사·에러, 캐시·스트리밍 지표는 모니터링 로그로 기록한다.

최종 완료 응답 직전에 이번 사용자·어시스턴트 메시지와 갱신된 요약을 Supabase의
`append_chat_turn` RPC 한 트랜잭션으로 기록한다. 저장이 성공한 완료 응답만 전달하므로
다음 턴의 S2는 누락 없이 최신 문맥을 로드한다.

## 직렬화 경계

State 객체 자체는 직렬화되지 않고 메모리에서 참조로 전달된다. 직렬화가 필요한 지점은 다음과 같다.

클라이언트로 나가는 응답은 스트리밍 형식(SSE 등)으로 직렬화된다. vLLM 호출은 해당 서비스의 요청 형식(JSON)을 따른다. 세션·히스토리는 Supabase Data API의 JSON 요청을 거쳐 정규화된 테이블 행으로 저장한다. 쿼리 캐시(Redis)에 저장하는 임베딩은 실수 배열이 크므로 JSON보다 바이너리 직렬화(msgpack 등)나 바이트 표현이 부피와 속도 면에서 유리하며, 청크 메타데이터와 벡터를 분리해 저장하는 방식도 고려할 수 있다.
