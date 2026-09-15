-- HEAPY v1 기존 데이터 보존 및 목표 스키마 변환
-- 작성자: 김진우

begin;

create schema if not exists migration_archive;
revoke all on schema migration_archive from public, anon, authenticated;

create table migration_archive.users_orphan_20260903 as
select app_user.*
from public.users as app_user
left join auth.users as auth_user
  on auth_user.id = app_user.user_id
where auth_user.id is null;

create table migration_archive.lifestyle_activity_20260903 as
table public.lifestyle_activity;
create table migration_archive.lifestyle_exercise_20260903 as
table public.lifestyle_exercise;
create table migration_archive.lifestyle_bio_20260903 as
table public.lifestyle_bio;
create table migration_archive.lifestyle_nutrition_20260903 as
table public.lifestyle_nutrition;

revoke all on all tables in schema migration_archive from public, anon, authenticated;

-- 사용자 프로필은 기존 값을 유지하고 온보딩용 열만 추가한다.
alter table public.users
  alter column name drop not null,
  alter column birth_date drop not null,
  alter column sex drop not null,
  add column if not exists height_cm numeric(5,2),
  add column if not exists weight_kg numeric(5,2),
  add column if not exists smoking_status text,
  add column if not exists alcohol_frequency text,
  add column if not exists allergies jsonb not null default '[]'::jsonb,
  add column if not exists health_cautions text,
  add column if not exists onboarding_step smallint not null default 1,
  add column if not exists onboarding_completed_at timestamptz;

update public.users
set chronic_conditions = coalesce(chronic_conditions, '[]'::jsonb);

alter table public.users
  alter column chronic_conditions set default '[]'::jsonb,
  alter column chronic_conditions set not null;

-- 기존 상담 기록은 그대로 두고 v1 문맥·모델 추적 열을 추가한다.
alter table public.chat_sessions
  add column if not exists summary_version integer not null default 0,
  add column if not exists companion_code text,
  add column if not exists last_message_at timestamptz;

update public.chat_sessions as session
set last_message_at = latest.last_message_at
from (
  select message.session_id, max(message.created_at) as last_message_at
  from public.chat_messages as message
  group by message.session_id
) as latest
where latest.session_id = session.session_id
  and session.last_message_at is null;

alter table public.chat_messages
  alter column role type text,
  alter column message_order type bigint,
  add column if not exists companion_code_snapshot text,
  add column if not exists response_status text not null default 'completed',
  add column if not exists model_name text,
  add column if not exists model_version text,
  add column if not exists prompt_version text;

-- 건강검진 기존 회차와 결과를 확장한다.
alter table public.master_checkup_item
  alter column item_code type text,
  alter column item_name type text,
  alter column standard_unit type text,
  add column if not exists item_category text not null default 'general',
  add column if not exists value_type text not null default 'numeric',
  add column if not exists display_order smallint not null default 0,
  add column if not exists is_active boolean not null default true,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

alter table public.health_checkup_records
  alter column user_id set not null,
  add column if not exists provider_name text,
  add column if not exists source_type text not null default 'manual',
  add column if not exists source_ocr_job_id uuid,
  add column if not exists source_fingerprint text,
  add column if not exists confirmed_at timestamptz not null default now(),
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

alter table public.health_checkup_results
  alter column item_code type text,
  alter column value type text,
  alter column status type text,
  alter column item_code set not null,
  add column if not exists numeric_value numeric,
  add column if not exists unit text,
  add column if not exists created_at timestamptz not null default now();

update public.health_checkup_results as result
set numeric_value = trim(result.value)::numeric
where result.numeric_value is null
  and result.value is not null
  and trim(result.value) ~ '^[+-]?[0-9]+([.][0-9]+)?$';

update public.health_checkup_results as result
set unit = item.standard_unit
from public.master_checkup_item as item
where item.item_code = result.item_code
  and result.unit is null;

-- 일간 활동은 한국 날짜별 한 행으로 유지한다.
alter table public.lifestyle_activity
  rename column activity_idid to activity_id;
alter table public.lifestyle_activity
  rename column floors_climbed to floors;
alter table public.lifestyle_activity
  rename column active_time to active_time_minutes;
alter table public.lifestyle_activity
  rename column active_distance to distance_m;
alter table public.lifestyle_activity
  rename column active_calories to active_calories_kcal;

alter table public.lifestyle_activity
  alter column steps type integer using round(steps)::integer,
  alter column floors type integer using round(coalesce(floors, 0))::integer,
  alter column active_time_minutes type integer using round(active_time_minutes)::integer,
  alter column distance_m type numeric using distance_m::numeric,
  alter column active_calories_kcal type numeric using active_calories_kcal::numeric,
  alter column source type text,
  add column if not exists external_record_id text,
  add column if not exists source_updated_at timestamptz,
  add column if not exists sync_run_id uuid,
  add column if not exists is_user_override boolean not null default false;

update public.lifestyle_activity
set source = case when source = 'manul' then 'manual' else coalesce(source, 'manual') end,
    updated_at = coalesce(updated_at, created_at, now());

alter table public.lifestyle_activity
  alter column steps set default 0,
  alter column floors set default 0,
  alter column floors set not null,
  alter column active_time_minutes set default 0,
  alter column distance_m set default 0,
  alter column active_calories_kcal set default 0,
  alter column source set default 'manual',
  alter column source set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null,
  drop column total_calories;

-- 운동 세션은 시작·종료 절대시각을 기준으로 정리한다.
alter table public.lifestyle_exercise
  rename column duration_sec to duration_seconds;
alter table public.lifestyle_exercise
  rename column calories to calories_kcal;
alter table public.lifestyle_exercise
  rename column detail_value to detail_data;

alter table public.lifestyle_exercise
  alter column exercise_type type text,
  alter column start_at type timestamptz using start_at at time zone 'Asia/Seoul',
  alter column end_at type timestamptz using end_at at time zone 'Asia/Seoul',
  alter column duration_seconds type integer using round(duration_seconds)::integer,
  alter column detail_data type jsonb using coalesce(detail_data::jsonb, '{}'::jsonb),
  alter column source type text,
  add column if not exists external_record_id text,
  add column if not exists source_updated_at timestamptz,
  add column if not exists sync_run_id uuid,
  add column if not exists is_user_override boolean not null default false;

update public.lifestyle_exercise
set source = case when source = 'manul' then 'manual' else coalesce(source, 'manual') end,
    updated_at = coalesce(updated_at, created_at, now());

alter table public.lifestyle_exercise
  alter column user_id set not null,
  alter column exercise_type set not null,
  alter column start_at set not null,
  alter column end_at set not null,
  alter column duration_seconds set not null,
  alter column detail_data set default '{}'::jsonb,
  alter column detail_data set not null,
  alter column source set default 'manual',
  alter column source set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null,
  drop column record_date;

-- 물 섭취와 수면을 기존 범용 테이블에서 전용 테이블로 이관한다.
create table public.lifestyle_water_intake (
  water_intake_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  consumed_at timestamptz not null,
  amount_ml numeric(7,2) not null,
  source text not null default 'manual',
  external_record_id text,
  source_updated_at timestamptz,
  sync_run_id uuid,
  is_user_override boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.lifestyle_water_intake (
  water_intake_id, user_id, consumed_at, amount_ml, source, created_at, updated_at
)
select
  nutrition_id,
  user_id,
  consumed_at,
  water_amount::numeric(7,2),
  case when source = 'manul' then 'manual' else coalesce(source, 'legacy') end,
  created_at,
  coalesce(updated_at, created_at, now())
from public.lifestyle_nutrition
where coalesce(water_amount, 0) > 0;

delete from public.lifestyle_nutrition
where lower(coalesce(nutrition_type, '')) = 'water'
   or coalesce(water_amount, 0) > 0;

alter table public.lifestyle_nutrition
  alter column nutrition_type type text,
  alter column meal_type type text,
  alter column title type text,
  alter column source type text,
  add column if not exists external_record_id text,
  add column if not exists source_updated_at timestamptz,
  add column if not exists sync_run_id uuid,
  add column if not exists is_user_override boolean not null default false;

update public.lifestyle_nutrition
set source = case when source = 'manul' then 'manual' else coalesce(source, 'manual') end,
    updated_at = coalesce(updated_at, created_at, now());

alter table public.lifestyle_nutrition
  alter column user_id set not null,
  alter column consumed_at set not null,
  alter column source set default 'manual',
  alter column source set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null,
  drop column water_amount;

create table public.lifestyle_sleep (
  sleep_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  start_at timestamptz not null,
  end_at timestamptz not null,
  total_sleep_minutes integer not null,
  awake_minutes integer,
  deep_sleep_minutes integer,
  light_sleep_minutes integer,
  rem_sleep_minutes integer,
  sleep_score numeric(5,2),
  source text not null default 'manual',
  external_record_id text,
  source_updated_at timestamptz,
  sync_run_id uuid,
  is_user_override boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.lifestyle_sleep (
  sleep_id, user_id, start_at, end_at, total_sleep_minutes,
  awake_minutes, deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes,
  sleep_score, source, created_at, updated_at
)
select
  bio_id,
  user_id,
  start_at at time zone 'Asia/Seoul',
  end_at at time zone 'Asia/Seoul',
  round(extract(epoch from (end_at - start_at)) / 60.0)::integer,
  round((detail_data::jsonb ->> 'awake_min')::numeric)::integer,
  round((detail_data::jsonb ->> 'deep_sleep_min')::numeric)::integer,
  round((detail_data::jsonb ->> 'light_sleep_min')::numeric)::integer,
  round((detail_data::jsonb ->> 'rem_sleep_min')::numeric)::integer,
  (detail_data::jsonb ->> 'sleep_score')::numeric(5,2),
  coalesce(source, 'legacy'),
  created_at,
  coalesce(updated_at, created_at, now())
from public.lifestyle_bio
where lower(bio_type) = 'sleep';

-- 생체 측정의 범용 값·단위·JSON을 지표별 명시 컬럼으로 펼친다.
alter table public.lifestyle_bio
  alter column bio_type type text,
  alter column measured_at type timestamptz using measured_at at time zone 'Asia/Seoul',
  alter column source type text,
  add column if not exists heart_rate_bpm numeric,
  add column if not exists blood_glucose_mg_dl numeric,
  add column if not exists is_fasting boolean,
  add column if not exists systolic_mmhg numeric,
  add column if not exists diastolic_mmhg numeric,
  add column if not exists pulse_bpm numeric,
  add column if not exists weight_kg numeric(5,2),
  add column if not exists bmi_value numeric(5,2),
  add column if not exists body_fat_percent numeric(5,2),
  add column if not exists skeletal_muscle_kg numeric(5,2),
  add column if not exists external_record_id text,
  add column if not exists source_updated_at timestamptz,
  add column if not exists sync_run_id uuid,
  add column if not exists is_user_override boolean not null default false;

update public.lifestyle_bio
set heart_rate_bpm = case when bio_type = 'heart_rate' then value end,
    blood_glucose_mg_dl = case when bio_type = 'blood_glucose' then value end,
    is_fasting = case when bio_type = 'blood_glucose' then (detail_data::jsonb ->> 'fasting')::boolean end,
    systolic_mmhg = case when bio_type = 'blood_pressure' then (detail_data::jsonb ->> 'systolic')::numeric end,
    diastolic_mmhg = case when bio_type = 'blood_pressure' then (detail_data::jsonb ->> 'diastolic')::numeric end,
    pulse_bpm = case when bio_type = 'blood_pressure' then (detail_data::jsonb ->> 'pulse')::numeric end,
    weight_kg = case when bio_type = 'weight' then value::numeric(5,2) end,
    bmi_value = case when bio_type = 'bmi' then value::numeric(5,2) end,
    source = case when source = 'manul' then 'manual' else coalesce(source, 'manual') end,
    updated_at = coalesce(updated_at, created_at, now());

delete from public.lifestyle_bio
where lower(bio_type) = 'sleep';

alter table public.lifestyle_bio
  alter column user_id set not null,
  alter column bio_type set not null,
  alter column measured_at set not null,
  alter column source set default 'manual',
  alter column source set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null,
  drop column start_at,
  drop column end_at,
  drop column value,
  drop column unit,
  drop column detail_data;

commit;
