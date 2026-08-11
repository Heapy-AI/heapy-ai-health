# Supabase DB 구성

이 폴더는 의료용어 검색을 위한 Supabase PostgreSQL migration을 관리합니다.

## 포함 파일

- `migrations/202608110001_medical_term_search.sql`
  - `medical_term`, `medical_term_alias`, `medical_term_alias_initial` 테이블 생성
  - 표준 검색어 정규화 함수 생성
  - trigram·Levenshtein·초성 부분열 검색 함수 생성
  - alias 초성 데이터를 자동 갱신하는 Trigger 생성

## 적용 순서

### 1. Supabase migration 적용

Supabase CLI로 프로젝트를 연결한 뒤 migration을 적용합니다.

```bash
supabase link --project-ref <project-ref>
supabase db push
```

SQL Editor에서 migration 파일을 직접 실행할 수도 있지만, 팀 작업에서는 migration 파일을 Git으로 관리하고 `db push`를 사용하는 것을 권장합니다.

### 2. 표준용어·alias 데이터 생성

migration은 테이블과 검색 로직만 만들고 실제 용어 데이터를 만들지는 않습니다. 원천 JSONL에서 적재 SQL을 생성합니다.

```bash
python database/build_medical_term_catalog.py \
  --chunk-root vdb/chunk > /tmp/medical_term_catalog.sql
```

생성된 SQL을 Supabase PostgreSQL에 실행합니다.

```bash
psql "$RDB_DSN" -f /tmp/medical_term_catalog.sql
```

`RDB_DSN`에는 Supabase Dashboard의 Connect 화면에서 발급한 PostgreSQL connection string을 사용합니다. 비밀번호와 API 키는 `.env`에만 두고 Git에 커밋하지 않습니다.

### 3. 애플리케이션 연결

앱 서버에 다음 환경변수를 설정합니다.

```env
RDB_DSN=postgresql://...
```

앱은 RDB의 `search_medical_terms()`를 통해 표준용어·alias 후보를 조회하고, 확정된 용어를 Pinecone/RAG 검색에 전달합니다.
