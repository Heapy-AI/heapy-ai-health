-- 작성자: 김진우
-- 원격 public 테이블의 대략적인 행 수와 RLS 상태를 확인한다.
select
  c.relname as table_name,
  coalesce(s.n_live_tup, 0)::bigint as estimated_rows,
  c.relrowsecurity as rls_enabled
from pg_catalog.pg_class as c
join pg_catalog.pg_namespace as n
  on n.oid = c.relnamespace
left join pg_catalog.pg_stat_user_tables as s
  on s.relid = c.oid
where n.nspname = 'public'
  and c.relkind in ('r', 'p')
order by c.relname;
