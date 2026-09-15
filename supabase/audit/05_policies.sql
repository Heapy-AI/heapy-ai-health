-- 작성자: 김진우
-- 원격 public 테이블의 RLS 정책을 추출한다.
select
  tablename as table_name,
  policyname as policy_name,
  roles,
  cmd,
  qual,
  with_check
from pg_catalog.pg_policies
where schemaname = 'public'
order by tablename, policyname;
