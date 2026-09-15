-- 작성자: 김진우
-- 배포 스키마의 키·인덱스·RLS·권한·특권 함수 이상 여부를 찾는다.
with public_tables as (
  select cls.oid, cls.relname, cls.relrowsecurity
  from pg_catalog.pg_class as cls
  join pg_catalog.pg_namespace as ns on ns.oid = cls.relnamespace
  where ns.nspname = 'public' and cls.relkind in ('r', 'p')
), findings as (
  select 'table_without_primary_key'::text as finding_type, table_info.relname::text as object_name
  from public_tables as table_info
  where not exists (
    select 1 from pg_catalog.pg_constraint as constraint_info
    where constraint_info.conrelid = table_info.oid and constraint_info.contype = 'p'
  )

  union all
  select 'public_table_without_rls', table_info.relname
  from public_tables as table_info
  where not table_info.relrowsecurity

  union all
  select 'foreign_key_without_index', constraint_info.conrelid::regclass::text || '.' || constraint_info.conname
  from pg_catalog.pg_constraint as constraint_info
  where constraint_info.contype = 'f'
    and constraint_info.connamespace in (
      'public'::regnamespace,
      'private'::regnamespace
    )
    and not exists (
      select 1
      from pg_catalog.pg_index as index_info
      where index_info.indrelid = constraint_info.conrelid
        and index_info.indisvalid
        and index_info.indkey::smallint[] @> constraint_info.conkey
    )

  union all
  select 'not_valid_constraint', constraint_info.conrelid::regclass::text || '.' || constraint_info.conname
  from pg_catalog.pg_constraint as constraint_info
  where constraint_info.connamespace in ('public'::regnamespace, 'private'::regnamespace)
    and not constraint_info.convalidated

  union all
  select 'anon_table_privilege', privilege.table_schema || '.' || privilege.table_name || ':' || privilege.privilege_type
  from information_schema.role_table_grants as privilege
  where privilege.grantee = 'anon' and privilege.table_schema in ('public', 'private')

  union all
  select 'authenticated_private_privilege', privilege.table_schema || '.' || privilege.table_name || ':' || privilege.privilege_type
  from information_schema.role_table_grants as privilege
  where privilege.grantee = 'authenticated' and privilege.table_schema = 'private'

  union all
  select 'public_security_definer_function', routine.oid::regprocedure::text
  from pg_catalog.pg_proc as routine
  join pg_catalog.pg_namespace as ns on ns.oid = routine.pronamespace
  where ns.nspname = 'public' and routine.prosecdef
)
select finding_type, object_name
from findings
order by finding_type, object_name;
