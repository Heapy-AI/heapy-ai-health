# Healpy AI health care 파이프라인 — 내부 State 설계 문서
Healpy AI health care의 요청 처리 파이프라인에서 노드 간에 흐르는 내부 State 객체의 설계를 정의한다. 이 문서는 프로세스 내부 데이터 모델을 다루며, 외부로 노출되는 API 계약(요청/응답 JSON)은 별도의 API 명세서에서 다룬다.

## 설계 원칙

파이프라인은 단일 State 객체를 노드에서 노드로 흘려보내는 방식으로 동작한다. 각 노드는 State를 입력으로 받아 자신이 담당하는 필드만 채우거나 갱신한 뒤 다음 노드로 넘긴다. 노드 간 전달은 직렬화 없이 메모리상 객체 참조로 이루어지며, 직렬화(JSON, 바이너리 등)는 프로세스·서비스 경계를 넘을 때(클라이언트 응답, vLLM 호출, Redis 저장)에만 발생한다.

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
| `resolved_query` | 문자열 | S3 또는 S4 | 재구성된 질문. 신규 세션은 원문과 동일 |
| `query_embedding` | 실수 배열 | A1 | 질문 임베딩 벡터. 캐시 조회·검색·저장에서 재사용 |
| `intent` | 열거형 | A4 | simple_lookup / comprehensive / general_chat / ignore |
| `guard_triggered` | 불리언 | SG | 의료 Safety Guard 작동 여부 |
| `guard_reason` | 문자열 또는 없음 | SG | definitive_diagnosis / medication_decision / medical_visit_decision |
| `sub_intents` | 문자열 목록 | B1 | 다중 선택 가능. 검색 대상 콜렉션과 매핑 |
| `chunks` | 청크 목록 또는 없음 | 검색/캐시 노드 | 검색 결과 청크. 아래 "chunks 상태 규약" 참조 |
| `cache_hit` | 불리언 | SC1 또는 BC1 | 캐시 히트 여부 |
| `user_context` | 객체 또는 없음 | D2 | RDB에서 조합한 개인 컨텍스트 (comprehensive 경로만) |
| `prompt` | 문자열 | C2 / B4 / C5 | LLM에 전달할 최종 프롬프트 |
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
| S1 세션 조회 | `raw_query` | `session_id` | HDB에서 세션 조회만 수행. 저장은 O3가 담당 |
| S1CHK 세션 존재 여부 | `session_id` | `is_new_session` | 기존/신규 분기 |
| S2 컨텍스트 로드 | `session_id` | `history`, `summary` | 기존 세션만. 요약은 직전 O3가 만들어 둔 것을 로드 |
| S3 질문 재구성 | `raw_query`, `history`, `summary` | `resolved_query` | 대명사·생략 복원 |
| S4 신규 세션 초기화 | `raw_query` | `resolved_query`, `history`(빈 목록) | 재구성 스킵, 원문 그대로 |

### 의도 분류 (Decider)

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| SG Safety Guard | `resolved_query` | `guard_triggered`, `guard_reason`, (차단 시)`intent` | 진단·약물 결정·내원 판단이면 임베딩 전에 ignore |
| A1 임베딩 변환 | `resolved_query` | `query_embedding` | Sentence-Transformers. 이후 캐시·검색에서 재사용 |
| A2 Linear Layer | `query_embedding` | (로짓, 내부) | 학습된 선형 분류기 |
| A3 Softmax | (로짓) | (확률 분포, 내부) | intent별 확률 |
| A4 Intent 분류 | (확률 분포) | `intent` | argmax + 임계값 |

### 검색 (Simple / Comprehensive 공통 패턴)

| 노드 | 입력 | 출력 | 비고 |
|---|---|---|---|
| B1 Sub-intent 분류 | `resolved_query`, `intent` | `sub_intents` | comprehensive만. 콜렉션 목록으로 매핑 |
| SC1 / BC1 캐시 조회 | `query_embedding` | `cache_hit`, (히트 시)`chunks` | 유사도 ≥ 임계값이면 히트 |
| C1 / B2 VDB 검색 | `query_embedding`, `sub_intents` | `chunks` | 캐시 미스 시 실행. top-k |
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
| B4 프롬프트 구성 (comprehensive) | `chunks`, `user_context`, `history`, `summary` | `prompt` | 검색·개인·히스토리·분석 지시 결합 |
| C5 프롬프트 구성 (chat) | `history`, `summary` | `prompt` | 자유 대화 |
| L1 LLM 호출 | `prompt` | (스트림 시작) | 스트리밍 모드 |
| L2 / L3 스트림 전송 | (LLM 토큰) | (출력으로 청크 전송) | 토큰 단위 전송 |
| B5 응답 검증 | (누적 응답) | (검증된 응답) | 누적 완료 후 스키마·안전성 검증 |

## State 라이프사이클

하나의 요청이 처리되는 동안 State가 채워지는 순서를 요약한다.

요청이 들어오면 S1이 세션을 조회하고 S1CHK가 신규 여부를 판정한다. 기존 세션이면 S2가 히스토리와 요약을 로드하고 S3가 질문을 재구성하며, 신규 세션이면 S4가 빈 히스토리로 초기화하고 원문을 그대로 사용한다. 이후 SG가 의료적 결정 요청을 먼저 확인한다. Guard가 작동하면 임베딩 없이 ignore로 라우팅하고, 통과한 질문만 A1이 임베딩을 생성한 뒤 A4가 intent를 결정한다.

intent가 simple 또는 comprehensive이면 먼저 캐시를 조회하고, 히트하면 저장된 청크를 재사용하며 미스이면 VDB를 검색한다. VDB 응답 성공을 확인한 뒤 검색 결과 유무를 판정하고, 결과가 있으면 캐시에 저장한 다음 프롬프트를 구성한다. comprehensive 경로는 이와 병렬로 인증을 거쳐 개인 컨텍스트를 조합하며, 이 개인 데이터는 캐시하지 않는다.

프롬프트가 완성되면 L1이 스트리밍으로 LLM을 호출하고, 토큰이 생성되는 대로 사용자에게 전송하면서 동시에 누적한다. 누적이 끝나면 B5가 응답을 검증한다. 이 모든 과정에서 분류 결과, 검증·에러, 캐시·스트리밍 지표가 각각 모니터링 로그로 기록된다.

응답이 사용자에게 모두 전송된 후, 후처리 단계에서 이번 턴을 히스토리에 추가하고 요약을 갱신하여 세션 저장소에 기록한다. 이 저장 작업은 사용자 응답 경로 밖에서 이루어지므로 체감 지연에 영향을 주지 않으며, 갱신된 요약은 다음 턴의 S2가 로드하게 된다.

## 직렬화 경계

State 객체 자체는 직렬화되지 않고 메모리에서 참조로 전달된다. 직렬화가 필요한 지점은 다음과 같다.

클라이언트로 나가는 응답은 스트리밍 형식(SSE 등)으로 직렬화된다. vLLM 호출은 해당 서비스의 요청 형식(JSON)을 따른다. 세션·히스토리 저장소(Redis)에 기록하는 히스토리는 JSON 문자열로 직렬화하는 것이 디버깅에 유리하다. 쿼리 캐시(Redis)에 저장하는 임베딩은 실수 배열이 크므로 JSON보다 바이너리 직렬화(msgpack 등)나 바이트 표현이 부피와 속도 면에서 유리하며, 청크 메타데이터와 벡터를 분리해 저장하는 방식도 고려할 수 있다.
