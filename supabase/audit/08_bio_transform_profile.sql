-- 작성자: 김진우
-- 생체·수면 레거시 값을 새 명시 컬럼으로 옮길 수 있는지 집계값으로 검증한다.
select
  bio_type,
  count(*) as row_count,
  min(value) as min_value,
  max(value) as max_value,
  count(*) filter (where start_at is not null) as start_count,
  count(*) filter (where end_at is not null) as end_count,
  min(extract(epoch from (end_at - start_at)) / 60.0) filter (where start_at is not null and end_at is not null) as min_duration_minutes,
  max(extract(epoch from (end_at - start_at)) / 60.0) filter (where start_at is not null and end_at is not null) as max_duration_minutes,
  count(*) filter (where detail_data::jsonb ? 'fasting') as fasting_count,
  count(*) filter (where detail_data::jsonb ? 'systolic') as systolic_count,
  count(*) filter (where detail_data::jsonb ? 'diastolic') as diastolic_count,
  count(*) filter (where detail_data::jsonb ? 'pulse') as pulse_count,
  count(*) filter (where detail_data::jsonb ? 'awake_min') as awake_count,
  count(*) filter (where detail_data::jsonb ? 'deep_sleep_min') as deep_count,
  count(*) filter (where detail_data::jsonb ? 'light_sleep_min') as light_count,
  count(*) filter (where detail_data::jsonb ? 'rem_sleep_min') as rem_count,
  count(*) filter (where detail_data::jsonb ? 'sleep_score') as sleep_score_count
from public.lifestyle_bio
group by bio_type
order by bio_type;
