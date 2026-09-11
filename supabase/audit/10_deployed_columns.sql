-- 작성자: 김진우
-- 배포된 public·private 컬럼 계약을 문서 재생성용으로 추출한다.
select
  table_schema,
  table_name,
  ordinal_position,
  column_name,
  data_type,
  udt_schema,
  udt_name,
  character_maximum_length,
  numeric_precision,
  numeric_scale,
  is_nullable,
  column_default,
  is_identity
from information_schema.columns
where table_schema in ('public', 'private')
order by table_schema, table_name, ordinal_position;
