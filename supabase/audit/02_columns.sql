-- 작성자: 김진우
-- 원격 public 테이블의 컬럼 계약을 추출한다.
select
  table_name,
  ordinal_position,
  column_name,
  data_type,
  udt_name,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
order by table_name, ordinal_position;
