-- 작성자: 김진우
-- 원격 public 테이블의 제약조건 정의를 추출한다.
select
  ns.nspname as schema_name,
  cls.relname as table_name,
  con.conname as constraint_name,
  con.contype as constraint_type,
  pg_get_constraintdef(con.oid, true) as definition
from pg_catalog.pg_constraint as con
join pg_catalog.pg_class as cls
  on cls.oid = con.conrelid
join pg_catalog.pg_namespace as ns
  on ns.oid = cls.relnamespace
where ns.nspname = 'public'
order by cls.relname, con.conname;
