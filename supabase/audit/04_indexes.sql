-- 작성자: 김진우
-- 원격 public 테이블의 인덱스 정의를 추출한다.
select
  tablename as table_name,
  indexname as index_name,
  indexdef as definition
from pg_catalog.pg_indexes
where schemaname = 'public'
order by tablename, indexname;
