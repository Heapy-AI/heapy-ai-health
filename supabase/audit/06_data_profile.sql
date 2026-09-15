-- 작성자: 김진우
-- 기존 데이터를 목표 스키마로 옮기기 전에 NULL·고아 행·중복·변환 가능 여부를 점검한다.
with profile as (
  select 'users'::text as table_name, 'sex_values'::text as check_name,
         jsonb_object_agg(sex, row_count) as result
  from (select sex, count(*) as row_count from public.users group by sex) as values_by_sex

  union all
  select 'users', 'auth_orphans', to_jsonb(count(*))
  from public.users as app_user
  left join auth.users as auth_user on auth_user.id = app_user.user_id
  where auth_user.id is null

  union all
  select 'health_checkup_records', 'null_or_orphan_users',
         jsonb_build_object(
           'null_users', count(*) filter (where record.user_id is null),
           'orphan_users', count(*) filter (where record.user_id is not null and app_user.user_id is null)
         )
  from public.health_checkup_records as record
  left join public.users as app_user on app_user.user_id = record.user_id

  union all
  select 'health_checkup_results', 'null_items_and_numeric_parse',
         jsonb_build_object(
           'null_item_code', count(*) filter (where item_code is null),
           'numeric_text', count(*) filter (where trim(value) ~ '^[+-]?[0-9]+([.][0-9]+)?$'),
           'non_numeric_text', count(*) filter (where value is not null and trim(value) !~ '^[+-]?[0-9]+([.][0-9]+)?$')
         )
  from public.health_checkup_results

  union all
  select 'lifestyle_activity', 'migration_safety',
         jsonb_build_object(
           'null_or_orphan_users', count(*) filter (where app_user.user_id is null),
           'duplicate_user_dates', (
             select count(*) from (
               select user_id, record_date from public.lifestyle_activity
               group by user_id, record_date having count(*) > 1
             ) as duplicates
           ),
           'fractional_steps', count(*) filter (where steps <> trunc(steps)),
           'fractional_floors', count(*) filter (where floors_climbed is not null and floors_climbed <> trunc(floors_climbed)),
           'negative_values', count(*) filter (where steps < 0 or coalesce(floors_climbed, 0) < 0 or active_time < 0 or active_distance < 0 or active_calories < 0)
         )
  from public.lifestyle_activity as activity
  left join public.users as app_user on app_user.user_id = activity.user_id

  union all
  select 'lifestyle_exercise', 'migration_safety',
         jsonb_build_object(
           'null_users', count(*) filter (where exercise.user_id is null),
           'orphan_users', count(*) filter (where exercise.user_id is not null and app_user.user_id is null),
           'null_type', count(*) filter (where exercise_type is null),
           'null_start', count(*) filter (where start_at is null),
           'null_end', count(*) filter (where end_at is null),
           'invalid_range', count(*) filter (where start_at is not null and end_at is not null and end_at <= start_at),
           'negative_values', count(*) filter (where coalesce(duration_sec, 0) < 0 or coalesce(distance_m, 0) < 0 or coalesce(calories, 0) < 0)
         )
  from public.lifestyle_exercise as exercise
  left join public.users as app_user on app_user.user_id = exercise.user_id

  union all
  select 'lifestyle_bio', 'migration_safety',
         jsonb_build_object(
           'null_users', count(*) filter (where bio.user_id is null),
           'orphan_users', count(*) filter (where bio.user_id is not null and app_user.user_id is null),
           'null_type', count(*) filter (where bio_type is null),
           'null_measured_at', count(*) filter (where measured_at is null),
           'sleep_rows', count(*) filter (where lower(coalesce(bio_type, '')) = 'sleep'),
           'negative_value', count(*) filter (where value < 0)
         )
  from public.lifestyle_bio as bio
  left join public.users as app_user on app_user.user_id = bio.user_id

  union all
  select 'lifestyle_nutrition', 'migration_safety',
         jsonb_build_object(
           'null_users', count(*) filter (where nutrition.user_id is null),
           'orphan_users', count(*) filter (where nutrition.user_id is not null and app_user.user_id is null),
           'null_consumed_at', count(*) filter (where consumed_at is null),
           'water_rows', count(*) filter (where coalesce(water_amount, 0) > 0),
           'negative_water', count(*) filter (where water_amount < 0),
           'negative_nutrients', count(*) filter (where calories < 0 or total_fat < 0 or carbohydrate < 0 or protein < 0 or sodium < 0)
         )
  from public.lifestyle_nutrition as nutrition
  left join public.users as app_user on app_user.user_id = nutrition.user_id

  union all
  select 'chat_messages', 'message_order_duplicates', to_jsonb(count(*))
  from (
    select session_id, message_order
    from public.chat_messages
    group by session_id, message_order
    having count(*) > 1
  ) as duplicates
)
select table_name, check_name, result
from profile
order by table_name, check_name;
