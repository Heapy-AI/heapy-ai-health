# Labs Item Master 파일 구조

```text
labs_master/
└── supabase/
    ├── 001_create_labs_item_master.sql
    ├── 002_seed_labs_item_master.sql
    ├── 003_seed_labs_item_alias.sql
    ├── 004_seed_labs_panel_item.sql
    └── 005_seed_labs_item_reference_range.sql
```

- `001`: 4개 테이블과 제약조건을 생성한다.
- `002`: 158개 표준 검사 항목을 입력한다.
- `003`: 250개 대표명·약어·동의어를 `item_code`로 연결한다.
- `004`: 39개 검사 패널과 구성 항목을 `item_code`로 연결한다.
- `005`: 14개 출처 확인 참고기준을 `item_code`로 연결한다.

Supabase SQL Editor에서 `001 → 005` 순서로 각 파일의 전체 내용을 실행한다. 모두 순수
PostgreSQL SQL이므로 `psql`, `\copy`, 로컬 CSV 파일이 필요 없다.

관계 시드 파일은 숫자 `item_id`를 직접 고정하지 않는다. 대신 `item_code`로 `item_id`를
조회해 연결하므로, Supabase에서 생성되는 ID 값과 무관하게 재실행할 수 있다.
