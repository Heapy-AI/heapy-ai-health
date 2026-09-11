-- 작성자: 김진우
-- HEAPY v1 migration 적용 후 테이블·데이터·RLS 핵심 불변조건을 검증한다.
select 'public_table_count' as check_name, count(*)::bigint as actual_value, 43::bigint as expected_value
from pg_catalog.pg_class as cls
join pg_catalog.pg_namespace as ns on ns.oid = cls.relnamespace
where ns.nspname = 'public' and cls.relkind in ('r', 'p')

union all
select 'public_tables_without_rls', count(*), 0
from pg_catalog.pg_class as cls
join pg_catalog.pg_namespace as ns on ns.oid = cls.relnamespace
where ns.nspname = 'public' and cls.relkind in ('r', 'p') and not cls.relrowsecurity

union all
select 'legacy_activity_archive_rows', count(*), 92
from migration_archive.lifestyle_activity_20260903
union all
select 'legacy_exercise_archive_rows', count(*), 29
from migration_archive.lifestyle_exercise_20260903
union all
select 'legacy_bio_archive_rows', count(*), 316
from migration_archive.lifestyle_bio_20260903
union all
select 'legacy_nutrition_archive_rows', count(*), 844
from migration_archive.lifestyle_nutrition_20260903

union all
select 'activity_rows', count(*), 92 from public.lifestyle_activity
union all
select 'exercise_rows', count(*), 29 from public.lifestyle_exercise
union all
select 'bio_rows_without_sleep', count(*), 224 from public.lifestyle_bio
union all
select 'sleep_rows', count(*), 92 from public.lifestyle_sleep
union all
select 'nutrition_food_rows', count(*), 331 from public.lifestyle_nutrition
union all
select 'water_rows', count(*), 513 from public.lifestyle_water_intake
union all
select 'transformed_lifestyle_total', (
  (select count(*) from public.lifestyle_activity) +
  (select count(*) from public.lifestyle_exercise) +
  (select count(*) from public.lifestyle_bio) +
  (select count(*) from public.lifestyle_sleep) +
  (select count(*) from public.lifestyle_nutrition) +
  (select count(*) from public.lifestyle_water_intake)
), 1281

union all
select 'chat_sessions_rows', count(*), 15 from public.chat_sessions
union all
select 'chat_messages_rows', count(*), 78 from public.chat_messages
union all
select 'checkup_record_rows', count(*), 4 from public.health_checkup_records
union all
select 'checkup_result_rows', count(*), 100 from public.health_checkup_results
union all
select 'medical_term_rows', count(*), 469 from public.medical_term
union all
select 'medical_term_alias_rows', count(*), 616 from public.medical_term_alias
union all
select 'medical_term_initial_rows', count(*), 4930 from public.medical_term_alias_initial
union all
select 'app_user_rows', count(*), 5 from public.users
union all
select 'archived_orphan_user_rows', count(*), 1 from migration_archive.users_orphan_20260903

order by check_name;
