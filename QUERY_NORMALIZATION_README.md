# HEAPY 검색어 오타·표준용어 보정 구현 안내

이 문서는 HEAPY 건강정보 검색에서 사용자가 의약품·질환·증상명을 오타로 입력해도 RDB의 표준 의료용어로 검색이 이어지도록 구현한 내용을 팀 공유용으로 정리한 문서입니다.

## 1. 해결한 문제

기존 검색은 사용자의 원문을 그대로 임베딩했습니다. 짧은 의약품명이나 질환명에 오타가 들어가면 Pinecone에서 전혀 다른 청크가 검색되거나 `지식베이스에 근거 없음`으로 끝날 수 있었습니다.

이번 구현에서는 검색 전에 다음 작업을 수행합니다.

```text
사용자 질문
  → 의료용어 후보 추출
  → RDB 표준명·별칭·오타 후보 검색
  → 신뢰도·모호성 검증
  → exact 후보는 canonical_name으로 질문 재작성
  → initials/fuzzy 후보는 예·아니요 확인 후 진행
  → 확인된 canonical_name으로 질문 재작성
  → 재작성된 질문 임베딩
  → Pinecone 검색 및 RAG 답변
```

예시:

| 사용자 입력 | 검색용으로 보정된 질문 | 연결된 표준용어 |
|---|---|---|
| `브르폔 먹고 배아팡` | 검색 보류 후 표준용어 확인 질문 | 이부프로펜 후보 |
| `ㅂㄹㅍ 머야?` | 검색 보류 후 표준용어 확인 질문 | 이부프로펜 후보 |
| `당냐뱡 어케하지` | 검색 보류 후 표준용어 확인 질문 | 당뇨병 후보 |
| `당나뼝 나 어떻게` | 검색 보류 후 표준용어 확인 질문 | 당뇨병 후보 |
| `타이레놀 효능` | `아세트아미노펜 효능` | 아세트아미노펜 |

## 2. 오타 보정 방식

핵심 구현은 [`app/services/query_resolver.py`](app/services/query_resolver.py)의 `MedicalQueryResolver`입니다.

### 2.1 입력 정규화

- Unicode NFKC 정규화
- 대소문자 통일
- 공백·구두점 차이 제거용 비교 키 생성
- 한글 호환 자모와 초성 입력 보존
- `고혈압이`처럼 조사로 끝나는 입력에서 `이`, `은`, `는`, `을`, `를` 등을 분리
- 질문 전체가 아니라 단어·2단어·3단어 조합을 우선 후보로 검색

따라서 질문 문맥은 보존하면서 의료용어가 포함된 부분만 표준명으로 바꿀 수 있습니다.

다만 `간이 아픈데 먹을만한 약 추천해줘` 또는 `위 아프면 먹을 수 있는 약 뭐였어?`처럼 증상 표현과 약을 고르는 문장 구조가 함께 들어오면 검색을 억지로 시도하지 않습니다. 특정 장기·질환·약품명을 코드에 추가하지 않고, 일반적인 증상 표현과 복약 요청 구조를 조합해 `Safety Guard`가 먼저 감지합니다. 이후 약을 임의로 추천하지 않고 진료 권고와 응급 위험 신호를 안내합니다.

`감기약 뭐였지?`처럼 증상 호소가 아닌 의약품 범주 조회는 별도로 처리합니다. `감기약`을 `감기` 질환명으로 축약하지 않고 원문 문맥을 보존하며, RDB 용어 타입 또는 일반적인 약물 어휘에서 `MEDICATION` 도메인 힌트를 만들어 의약품 namespace를 우선 검색합니다. 따라서 `감기의 증상`은 질환 정보로, `감기약`은 의약품 정보로 분리됩니다.

### 2.2 후보 점수

RDB 또는 로컬 저장소에서 다음 순서로 후보를 평가합니다.

| match_kind | 의미 | 기본 점수 |
|---|---|---:|
| `exact` | 표준명 또는 별칭과 완전 일치 | 1.00 |
| `substring` | 입력 안에 별칭이 포함되거나 입력이 별칭의 일부 | 0.96 |
| `initials` | 한글 초성열이 일치 | 0.92 |
| `initials` | 초성만 입력한 경우 | 0.97 |
| `initials_substring` | 표준명 내부 초성 부분열이 일치 | 0.88 |
| `fuzzy` | trigram·word similarity·Levenshtein 기반 유사 후보 | 계산값 |

초성은 다음과 같이 처리합니다.

- `브르폔`, `부루펜` → `ㅂㄹㅍ`
- `당냐뺭`, `당나뼝`, `당뇨병` → 기본 초성열 `ㄷㄴㅂ`
- `고혈압` → `혈압` → `ㅎㅇ`처럼 표준명 내부의 연속 구간도 자동 파생
- `ㅂ/ㅃ`, `ㄷ/ㄸ`, `ㄱ/ㄲ`처럼 된소리와 기본소리는 같은 초성 그룹으로 비교

### 2.3 오인식 방지

모든 유사 후보를 무조건 적용하지 않습니다.

- 기본 최소 점수: `0.66`
- 1위와 2위 후보의 점수 차이가 `0.05` 미만이면 모호한 후보로 판단
- 같은 질문에서 최대 3개 표준용어까지만 적용
- 정확·부분 일치를 제외한 약한 후보는 초성·trigram·음절 구성 등 독립 근거가
  둘 이상 맞아야 통과
- 완성형 동사·형용사 활용형은 의료용어 후보가 아니라 문맥으로 보존
- 동점·모호하거나 오타로 판정된 경우 원문 질문을 유지하고 확인 질문을 표시
- RDB 연결 오류가 발생하면 원문 검색으로 안전하게 fallback

일반 한글 음절을 초성으로 오해하지 않도록 초성 분기를 실제 자모 입력으로
제한합니다. 따라서 `ㅎㅇ`은 RDB alias에서 파생된 `혈압` 후보가 될 수 있지만,
`하이`는 같은 초성열이라는 이유만으로 혈압에 연결되지 않습니다. 음절 오타는
초성열이 같고 초성·중성·종성 구성 유사도가 충분할 때만 `initials` 후보가 되며,
그 후보는 예/아니요 확인을 거칩니다. 낮은 점수의 `fuzzy` 후보는 별도의
`fuzzy_min_score`(기본 0.70)를 통과하지 못하면 버립니다.

즉, 검색 결과를 넓히되 임의로 진단명이나 복약 정보를 만들어내지는 않습니다.

해석 결과는 `QueryResolution.resolution_status`로 구분합니다.

| 상태 | 의미 | 다음 동작 |
|---|---|---|
| `RESOLVED` | 정확한 표준명·alias가 확인됨 | canonical name을 포함해 검색 |
| `CONFIRM` | 초성·음절 오타 후보가 하나로 좁혀짐 | 예/아니요 확인 후 검색 |
| `AMBIGUOUS` | 여러 표준용어가 비슷한 점수로 경쟁함 | 검색하지 않고 용어를 더 입력하도록 안내 |
| `NO_MATCH` | 용어 사전에서 충분한 후보를 찾지 못함 | 원문 검색 또는 근거 없음 처리 |

`ㄱㅎㅇ`처럼 alias가 여러 문서에서 중복 발견되는 경우에는 표준명과 관련어의
우선순위를 비교합니다. 다른 항목의 관련어가 별도 항목의 표준명과 같으면
표준명 소유 항목을 우선하고, 서로 다른 표준용어가 실제로 경쟁하면
`AMBIGUOUS`로 남깁니다. 특정 용어를 코드에 매핑하지 않는 일반 규칙입니다.

같은 유형의 여러 표준항목이 하나의 사용자 표현을 공유하는 경우에는 alias
그룹으로 검색합니다. 예를 들어 여러 검사항목이 `간수치`를 관련어로 가지면
`간수치`는 특정 AST·ALT 하나로 강제하지 않고 공통 검색어로 사용하며,
`ㄱㅅㅊ`·`갼슈치`는 `간수치` 확인 질문으로 연결합니다. 질환·증상처럼 서로
다른 유형이 같은 표현을 공유하면 기존처럼 `AMBIGUOUS`로 보류합니다.

### 2.4 오인식 가능 입력은 먼저 재질문

초성뿐 아니라 음절이 틀린 입력도 후보가 하나로 보이더라도 바로 검색하지 않습니다. 예를 들어 RDB의 alias 검색이 `ㄱㅅㅊ` 또는 `갼슈치`를 `간수치` 후보와 연결하면 다음처럼 확인 응답을 반환합니다.

```text
사용자: ㄱㅅㅊ 했어?
챗봇: 혹시 '간수치(AST)'를 물어보신 걸까요?

사용자: 갼슈치 알려줘
챗봇: 혹시 '간수치(AST)'를 물어보신 걸까요?
```

이 동작은 `간수치`, `AST` 같은 용어를 코드에 등록해서 만드는 방식이 아닙니다.

- RDB가 반환한 `matched_alias`, `canonical_name`, `term_type`으로 후보를 구성합니다.
- 검색 요청과 임베딩 생성을 보류하고 `query_confirmation=true`를 반환합니다.
- 사용자가 정확한 별칭 또는 표준명을 다시 입력하면 일반 정규화·검색 경로로 진행합니다.
- 정확한 표준명·alias는 바로 검색하고, `initials`·`fuzzy` 후보는 예/아니요 확인 후 검색합니다.

웹 UI에서는 이 확인 응답에 `예`와 `아니요` 버튼을 함께 표시합니다.

- `예`: 서버가 발급한 `confirmation_id`로 확인 후보를 확정한 뒤, 원문을
  resolver에 다시 통과시키지 않고 canonical term으로 검색합니다.
- `아니요`: 서버 검색을 호출하지 않고 새 검색어를 입력하도록 안내합니다.
- API 클라이언트는 `query_confirmation`, `confirmation_question`,
  `confirmation_id`, `resolved_terms`를 이용해 동일한 선택 UI를 구현할 수 있습니다.

확인 상태는 기본 로컬 서버에서 10분 동안 유지됩니다. 운영 환경에서는
`QueryConfirmationStore`를 Redis 같은 공유 저장소로 교체할 수 있습니다.

### 2.5 의료용어와 문맥 분리

질문 안의 모든 어절을 의료용어 후보로 만들지 않습니다. 명사·약어·초성은
의료용어 후보 레인으로 보내고, 동사·형용사·활용 어미는 상태·행동 문맥으로
보존합니다.

```text
간수치가 낮게 나왔어
 ├─ 간수치가 → 의료용어 후보
 ├─ 낮게     → 수치 상태 문맥
 └─ 나왔어   → 서술 문맥
```

따라서 문장 속 `나왔어`가 DB의 `나일열` alias와 초성 일부가 비슷하더라도,
약한 부분열 근거만으로 표준용어 확인 질문을 만들지 않습니다. DB alias와
정확히 일치하는 증상 표현은 예외적으로 허용하므로 증상 검색 범위는 보존됩니다.

## 3. RDB 구조

마이그레이션 파일은 [`database/migrations/001_medical_term_search.sql`](database/migrations/001_medical_term_search.sql)입니다.

### 3.1 테이블

`medical_term`은 의료용어의 기준 테이블입니다.

| 컬럼 | 설명 |
|---|---|
| `canonical_key` | 시스템 전체에서 사용하는 표준 키 |
| `canonical_name` | 사용자 질문으로 재작성할 정확한 표준명 |
| `term_type` | `MEDICATION`, `DISEASE`, `SYMPTOM`, `SCREENING` 등 |
| `is_active` | 검색 활성화 여부 |

`medical_term_alias`는 별칭·제품명·사용자 표현을 관리합니다.

| 컬럼 | 설명 |
|---|---|
| `alias_display` | 실제 사용자가 입력할 수 있는 표현 |
| `alias_normalized` | 공백·구두점 제거 후 비교 키 |
| `alias_initials` | 한글 초성 비교용 생성 컬럼 |
| `alias_type` | `CANONICAL`, `SYNONYM`, `BRAND`, `ABBREVIATION`, `USER_ALIAS` |
| `priority` | 같은 점수일 때 우선순위 |

`medical_term_alias_initial`은 alias를 저장할 때 한글 연속 구간의 초성 부분열을 자동 생성하는 보조 테이블입니다. 애플리케이션 코드에 `ㅎㅇ=혈압` 같은 매핑을 넣지 않고, RDB alias에서 `고혈압 → 혈압 → ㅎㅇ` 후보를 파생합니다.

### 3.2 검색 함수

`search_medical_terms(p_query, p_limit)` 함수가 다음 후보를 반환합니다.

- `canonical_key`
- `canonical_name`
- `term_type`
- `matched_alias`
- `match_score`
- `match_kind`

사용하는 PostgreSQL 기능:

- `pg_trgm`
- `fuzzystrmatch`
- trigram `similarity`
- `word_similarity`
- `levenshtein`
- 한글 초성 생성 함수 `normalize_medical_initials`
- alias 초성 부분열 생성 함수 `medical_initial_substrings`
- 초성 부분열 검색 인덱스 `idx_medical_term_alias_initial_key`
- 실제 초성 자모 입력 판별 함수 `is_medical_initial_input`

## 4. 운영 적용 방법

### 4.1 패키지 설치

```bash
pip install -r requirements.txt
```

RDB 연결을 사용하는 경우 `psycopg[binary]`가 필요합니다.

### 4.2 마이그레이션 적용

```bash
psql "$RDB_DSN" -f database/migrations/001_medical_term_search.sql
```

기존 `.env`에 다음 값을 설정합니다.

```env
RDB_DSN=postgresql://user:password@host:5432/database
QUERY_RESOLUTION_MIN_SCORE=0.66
QUERY_RESOLUTION_AMBIGUITY_MARGIN=0.05
```

`RDB_DSN`이 비어 있으면 `NullMedicalTermRepository`가 사용되어 기존 원문 검색으로 동작합니다.

중요한 데이터 연결 조건:

- 벡터 청크에 `저혈압` 본문이 있어도 `medical_term`·`medical_term_alias`에 표준용어가
  적재되지 않으면 `ㅈㅎㅇ` 같은 입력을 확인 질문으로 만들 수 없습니다. 본문 검색과
  질의 표준화 사전은 별도 저장소입니다.
- `혈당`은 건강검진 청크의 `공복혈당`과 연결되어야 하며, 당뇨병·고혈당·저혈당을
  별도 질환으로 답하려면 해당 canonical term과 alias 및 근거 청크를 각각 등록해야
  합니다.
- `medication_info` namespace에 JSONL 청크 또는 Pinecone vector가 없으면 약 이름을
  찾아 답할 수 없습니다. `GET /health`의 namespace별 count에서 0인지 먼저 확인합니다.

### 4.3 표준용어 데이터 적재

서비스에서 사용할 기준명과 별칭은 원천 JSONL metadata와 `관련어`에서 자동으로
추출해 SQL로 생성합니다. 코드 안에 의료용어를 직접 입력하지 않습니다.

```bash
python database/build_medical_term_catalog.py \
  --chunk-root vdb/chunk > /tmp/medical_term_catalog.sql
psql "$RDB_DSN" -f /tmp/medical_term_catalog.sql
```

생성기는 표준명 `100`, metadata alias `60`, 본문 `관련어` `30`의 우선순위를
데이터에서 계산합니다. 초성·trigram·편집거리용 키는 SQL에 직접 등록하지 않고
migration의 생성 컬럼과 검색 함수가 alias에서 자동 계산합니다.

수동 적재가 필요한 외부 DB alias가 있다면 아래 테이블에 추가할 수 있지만,
오타·초성 표현을 하나씩 등록하는 용도로 사용하지 않습니다.

```sql
INSERT INTO medical_term (canonical_key, canonical_name, term_type)
VALUES ('IBUPROFEN', '이부프로펜', 'MEDICATION')
ON CONFLICT (canonical_key) DO UPDATE
SET canonical_name = EXCLUDED.canonical_name,
    term_type = EXCLUDED.term_type,
    updated_at = NOW();

INSERT INTO medical_term_alias
    (canonical_key, alias_display, alias_type, priority)
VALUES
    ('IBUPROFEN', '이부프로펜', 'CANONICAL', 100),
    ('IBUPROFEN', '부루펜', 'BRAND', 80),
    ('IBUPROFEN', '브루펜', 'USER_ALIAS', 60)
ON CONFLICT (canonical_key, alias_normalized) DO UPDATE
SET priority = EXCLUDED.priority,
    is_active = TRUE;
```

질환·증상·검진 항목도 동일한 방식으로 등록합니다. 기준명은 하나로 유지하고, 제품명이나 사용자 표현은 alias로 분리하는 것이 좋습니다.

### 4.4 일반 서버 실행

운영 데이터와 Pinecone을 사용하는 기본 서버는 다음 명령으로 실행합니다.

```bash
uvicorn app.main:app --reload
```

서버 시작 시 [`app/main.py`](app/main.py)가 다음 객체를 준비합니다.

1. `RDB_DSN`으로 `MedicalQueryResolver` 생성
2. `PineconeSearchService`에 resolver 주입
3. `/search`, `/ask`, `/chat` 경로가 같은 resolver를 공유
4. `Safety Guard`에도 같은 `QueryResolution`을 전달해 RDB 용어 메타데이터를 사용
5. 초성 확인이 필요하면 검색·임베딩을 보류하고 재질문
6. 그 외에는 보정된 질문을 임베딩한 뒤 Pinecone 검색

## 5. 코드 연결 지점

| 파일 | 역할 |
|---|---|
| `app/services/query_resolver.py` | 용어 후보 추출·점수화·표준명 재작성 |
| `app/services/vector_search.py` | 보정 질문 임베딩 및 Pinecone 검색 |
| `app/services/chat_orchestrator.py` | 챗봇 분류 전에 질문 보정 |
| `app/services/safety_guard.py` | RDB 용어 메타데이터와 일반 요청 행위를 조합해 안전 응답으로 분기 |
| `app/routers/ask.py` | `/search`, `/ask`, 통합 검색 응답에 보정 결과 포함 |
| `app/routers/chat.py` | `/chat`, `/chat/stream` 응답에 보정 결과 포함 |
| `app/schemas/health_chatbot.py` | `resolved_query`, `resolved_terms` 응답 필드 정의 |
| `app/web/assets/app.js` | 화면에 표준용어 보정 내역과 초성 확인 `예/아니요` 버튼 표시 |
| `database/migrations/001_medical_term_search.sql` | RDB 테이블·함수·인덱스 생성 |

## 6. API 응답에서 확인하는 방법

`/chat` 응답에는 다음 필드가 포함됩니다.

```json
{
  "question": "브르폔 먹고 배아팡",
  "resolved_query": "브르폔 먹고 배아팡",
  "resolved_terms": [
    {
      "input": "브르폔",
      "canonical_key": "IBUPROFEN",
      "canonical_name": "이부프로펜",
      "term_type": "MEDICATION",
      "score": 0.92,
      "match_kind": "initials",
      "matched_alias": "부루펜"
    }
  ],
  "query_confirmation": true,
  "confirmation_question": "혹시 '부루펜(이부프로펜)'을 물어보신 걸까요?",
  "resolution_status": "CONFIRM"
}
```

`resolved_terms`가 비어 있으면 보정 후보가 임계값을 통과하지 못한 것이며, 이 경우 `resolved_query`는 원문과 같습니다.

초성 입력이 확인 대기 상태이면 다음 필드로 검색 보류를 식별할 수 있습니다.

```json
{
  "resolved_query": "ㄱㅅㅊ 했어?",
  "query_confirmation": true,
  "confirmation_question": "혹시 '간수치(AST)'를 물어보신 걸까요?",
  "verification_method": "query_confirmation"
}
```

검색만 확인할 때는 다음 요청을 사용할 수 있습니다.

```bash
curl -sS http://127.0.0.1:8000/search/combined \
  -H 'Content-Type: application/json' \
  -d '{"question":"당나뼝 나 어떻게"}'
```

## 7. 로컬 테스트하기

기본 모드는 Pinecone·Gemini·RDB 없이 보정 흐름을 확인하지만, workspace에 있는
`vdb/chunk/*.jsonl`이 있으면 그 원문 청크를 우선 읽습니다. 따라서 로컬에서도
현재 보유한 질환·검진 데이터의 검색 가능 여부를 확인할 수 있습니다. JSONL이
없으면 의료용어 fixture를 사용하지 않고 근거 없음으로 처리합니다. 같은 서버에 실제 Gemini 답변 모드도
포함되어 있어, 로컬 문서 검색 결과를 Gemini의 근거 계획·답변 생성·사후 감사
단계까지 통과시켜 볼 수 있습니다.

관련 파일:

- [`app/services/medical_term_catalog.py`](app/services/medical_term_catalog.py): 원천 metadata/관련어 기반 표준용어·alias catalog 생성
- [`database/build_medical_term_catalog.py`](database/build_medical_term_catalog.py): RDB 적재용 SQL 생성기
- [`app/services/local_dev.py`](app/services/local_dev.py): catalog와 실제 workspace 문서 기반 로컬 검색 구현
- [`app/services/query_confirmation.py`](app/services/query_confirmation.py): 예/아니요 확인 상태 저장소
- [`app/local_dev_server.py`](app/local_dev_server.py): FastAPI 로컬 진입점

외부 키 없는 데모 실행:

```bash
GOOGLE_API_KEY=local-demo-key \
PYTHONPATH=. \
python3 -m uvicorn app.local_dev_server:app --host 127.0.0.1 --port 8000
```

접속 주소:

- 웹 UI: <http://127.0.0.1:8000/>
- Swagger: <http://127.0.0.1:8000/docs>
- 상태 확인: <http://127.0.0.1:8000/health>

실제 Gemini 답변 모드 실행:

```bash
GOOGLE_API_KEY=your_gemini_api_key \
LOCAL_LLM_ENABLED=1 \
PYTHONPATH=. \
python3 -m uvicorn app.local_dev_server:app --host 127.0.0.1 --port 8000
```

또는 프로젝트 루트 `.env`에 `GOOGLE_API_KEY`를 넣고 다음처럼 실행합니다.

```bash
LOCAL_LLM_ENABLED=1 PYTHONPATH=. \
python3 -m uvicorn app.local_dev_server:app --host 127.0.0.1 --port 8000
```

화면의 `Answer generation`과 `GET /health`의 `llm_backend`가 `GEMINI`이면 실제
LLM 모드입니다. 로컬 데모는 `LOCAL_DEMO`로 표시됩니다. 현재 checkout의 로컬
청크 수는 `health_checkup_info=30`, `disease_info=15349`,
`medication_info=0`이므로, 로컬 `/health`가 `ready=false`인 것은 서버가 꺼진
상태가 아니라 복약 namespace가 비어 있다는 뜻입니다. 실제 LLM 모드도 검색
문서는 로컬 청크를 사용하므로 Pinecone 없이 답변 생성 단계를 검증할 수 있지만,
표준용어 확인 질문은 운영 RDB, 최종 검색 품질은 운영 Pinecone에서 별도로
검증해야 합니다.

## 8. 테스트

현재 오타 보정 및 웹 응답 회귀 테스트:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=. \
python3 -m unittest tests/test_query_resolver.py tests/test_web_ui.py
```

Safety Guard까지 포함한 통합 회귀 테스트:

```bash
GOOGLE_API_KEY=local-demo-key \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=. \
python3 -m unittest tests/test_safety_guard.py tests/test_chat_orchestrator.py tests/test_query_resolver.py tests/test_web_ui.py
```

검증한 주요 케이스:

- 일반 오타: `당뇨뼝` → 표준용어 확인 질문
- 초성 입력: `ㄱㅅㅊ` → `간수치` alias 그룹 확인 질문
- 모음·종성 혼동: `브르폔`, `갼슈치` → 표준용어 확인 질문
- 된소리 혼동: `당냐뺭`, `당나뼝` → 표준용어 확인 질문
- 브랜드명: `타이레놀` → `아세트아미노펜`
- 조사 제거: `고혈압이` → `고혈압` 후보 검색
- 초성 부분열: `ㅎㅇ` → `혈압(고혈압)` 확인 질문
- 서로 다른 유형의 모호한 동점 후보: 원문 유지
- 증상 + 약 추천: 근거 없음 대신 안전한 진료·응급 신호 안내

## 9. 운영 전 체크리스트

- [ ] 운영 PostgreSQL에 migration 적용
- [ ] 생성기로 만든 의약품·질환·증상·검진 표준용어를 운영 RDB에 적재
- [ ] canonical alias와 브랜드 alias를 분리
- [ ] 사용자 검색 로그에서 자주 실패하는 표현을 `USER_ALIAS`로 검토 후 추가
- [ ] 의료용어명·별칭·초성 후보를 검색엔진 코드에 하드코딩하지 않고 RDB로 관리
- [ ] Safety Guard가 특정 질환명·장기명 목록이 아니라 RDB 용어 메타데이터와 일반 요청 행위로 동작하는지 확인
- [ ] `RDB_DSN`, 점수 임계값, ambiguity margin 설정
- [ ] 실제 Pinecone namespace별 검색 결과 확인
- [ ] `confirmation_id` 만료·중복 클릭·재시도 흐름 확인
- [ ] `/chat` 응답의 `resolved_query`, `resolved_terms` 모니터링
- [ ] 모호한 용어가 잘못된 표준명으로 강제 치환되지 않는지 확인
- [ ] 의료적 판단이나 복약 지시를 오타 보정 로직에서 생성하지 않는지 확인

## 10. 안전·한계

이 기능은 검색 품질을 높이기 위한 용어 연결 기능입니다. 표준명으로 보정되었다고 해서 사용자의 질환이 확정되거나 특정 약의 복용이 권장되는 것은 아닙니다.

운영 코드에는 특정 질환명·장기명·약품명 목록을 두지 않습니다. 검색 후보와 용어 메타데이터는 RDB에서 받고, 코드는 텍스트 정규화·점수 계산·모호성 확인·초성 재질문 같은 일반 알고리즘만 수행합니다. Safety Guard도 같은 RDB 용어 메타데이터와 일반적인 요청 행위를 조합합니다. 로컬도 별도 의료용어 fixture가 아니라 실제 workspace corpus에서 같은 catalog 생성기를 사용합니다.

특히 다음 경우에는 원문을 유지하거나 의료진 확인이 필요한 응답으로 처리해야 합니다.

- 점수가 낮은 후보만 존재하는 경우
- 서로 다른 표준용어가 비슷한 점수로 경쟁하는 경우
- 약 이름과 성분명이 혼재해 사용자의 의도가 불분명한 경우
- 질문이 검색이 아니라 응급 증상·복약 변경·진단 요청에 해당하는 경우

로컬 데모는 문서별 토큰 인덱스와 질문 정규화 캐시를 서버 시작 시 생성합니다.
따라서 매 요청마다 전체 문서의 토큰화를 반복하지 않으며, 운영 환경에서는
RDB의 trigram/초성 인덱스와 Pinecone namespace 필터를 함께 사용해야 합니다.

실제 서비스 배포 전에는 생성된 표준용어 사전의 범위, alias 소유권 충돌, 모호성 비율과 alias 품질을 별도로 검수해야 합니다.
