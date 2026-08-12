# 의료용어 정규화 DB 설계

- 작성자: 김진우

## 목적

멀티턴으로 복원된 질문의 질환명·검사명·의약품명과 별칭을 표준용어에 연결한다.
이 저장소는 검색어를 보정할 뿐 진단이나 복약 결정을 생성하지 않는다.

## 테이블

| 테이블 | 역할 | 주요 키 |
|---|---|---|
| `medical_terms` | 표준용어와 유형 저장 | `canonical_key` |
| `medical_term_aliases` | 표준명·브랜드명·관련어·사용자 검수 별칭 저장 | `alias_id`, `(canonical_key, alias_normalized)` |

별칭에는 화면 표시값, 정규화값, 한글 초성값, 우선순위와 출처 유형을 저장한다.
개인 의료정보나 사용자 식별정보는 이 사전에 저장하지 않는다.

## 검색 계약

`search_medical_terms(input_query, result_limit)`는 표준 키·표준명·유형·일치 별칭,
점수, 일치 방식과 우선순위를 반환한다. 정확 일치, 부분 일치, 초성 일치,
PostgreSQL trigram 유사도 순으로 후보를 비교하며 애플리케이션이 최종 확인·모호성
임계값을 적용한다.

스키마와 함수는 `database/migrations/001_medical_term_search.sql`에서 관리한다.
운영 환경에서는 `RDB_DSN` 또는 `DATABASE_URL`을 설정하고 별칭 데이터를 검수한 뒤
적재한다. 연결 장애 시 챗봇은 원문 질문으로 폴백하고 `resolution_error`를 기록한다.
