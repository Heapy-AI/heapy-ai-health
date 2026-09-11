-- HEAPY v1 제약조건·인덱스·RLS·권한 적용
-- 작성자: 김진우

begin;

-- 기존 데이터 검증을 통과한 제약부터 활성화한다. auth 고아 사용자 1행 때문에
-- users_auth_user_id_fkey는 기존 NOT VALID 상태를 유지하고 별도 확인 대상으로 둔다.
alter table public.users drop constraint if exists users_sex_check;
alter table public.users
  add constraint users_sex_check check (sex is null or sex in ('Male', 'Female')) not valid,
  add constraint users_height_cm_check check (height_cm is null or height_cm between 30 and 250) not valid,
  add constraint users_weight_kg_check check (weight_kg is null or weight_kg between 2 and 500) not valid,
  add constraint users_smoking_status_check check (smoking_status is null or smoking_status in ('never', 'former', 'current')) not valid,
  add constraint users_alcohol_frequency_check check (alcohol_frequency is null or alcohol_frequency in ('none', 'monthly_1_2', 'weekly_1_2', 'weekly_3_plus')) not valid,
  add constraint users_chronic_conditions_array_check check (jsonb_typeof(chronic_conditions) = 'array') not valid,
  add constraint users_allergies_array_check check (jsonb_typeof(allergies) = 'array') not valid,
  add constraint users_onboarding_step_check check (onboarding_step between 1 and 6) not valid,
  add constraint users_onboarding_completion_check check (
    onboarding_completed_at is null or (
      name is not null and birth_date is not null and sex is not null and
      height_cm is not null and weight_kg is not null and
      smoking_status is not null and alcohol_frequency is not null
    )
  ) not valid;

alter table public.users validate constraint users_sex_check;
alter table public.users validate constraint users_height_cm_check;
alter table public.users validate constraint users_weight_kg_check;
alter table public.users validate constraint users_smoking_status_check;
alter table public.users validate constraint users_alcohol_frequency_check;
alter table public.users validate constraint users_chronic_conditions_array_check;
alter table public.users validate constraint users_allergies_array_check;
alter table public.users validate constraint users_onboarding_step_check;
alter table public.users validate constraint users_onboarding_completion_check;

alter table public.chat_messages
  add constraint chat_messages_session_order_uq unique (session_id, message_order);

alter table public.health_checkup_records
  add constraint health_checkup_records_source_type_check check (source_type in ('manual', 'ocr', 'import')),
  add constraint health_checkup_records_fingerprint_uq unique (user_id, source_fingerprint);

alter table public.health_checkup_results
  add constraint health_checkup_results_record_item_uq unique (record_id, item_code);

alter table public.lifestyle_activity
  add constraint lifestyle_activity_user_date_uq unique (user_id, record_date),
  add constraint lifestyle_activity_nonnegative_check check (
    steps >= 0 and distance_m >= 0 and floors >= 0 and
    active_time_minutes >= 0 and active_calories_kcal >= 0
  ),
  add constraint lifestyle_activity_source_check check (source in ('manual', 'samsung_health', 'legacy'));

alter table public.lifestyle_exercise
  add constraint lifestyle_exercise_range_check check (end_at > start_at),
  add constraint lifestyle_exercise_nonnegative_check check (
    duration_seconds >= 0 and coalesce(distance_m, 0) >= 0 and coalesce(calories_kcal, 0) >= 0
  ),
  add constraint lifestyle_exercise_source_check check (source in ('manual', 'samsung_health', 'legacy'));

alter table public.lifestyle_bio
  add constraint lifestyle_bio_source_check check (source in ('manual', 'samsung_health', 'legacy')),
  add constraint lifestyle_bio_type_check check (
    bio_type in ('heart_rate', 'blood_glucose', 'blood_pressure', 'weight', 'bmi', 'body_composition')
  ),
  add constraint lifestyle_bio_value_shape_check check (
    (bio_type = 'heart_rate' and heart_rate_bpm is not null) or
    (bio_type = 'blood_glucose' and blood_glucose_mg_dl is not null) or
    (bio_type = 'blood_pressure' and systolic_mmhg is not null and diastolic_mmhg is not null) or
    (bio_type = 'weight' and weight_kg is not null) or
    (bio_type = 'bmi' and bmi_value is not null) or
    (bio_type = 'body_composition' and (body_fat_percent is not null or skeletal_muscle_kg is not null))
  ),
  add constraint lifestyle_bio_nonnegative_check check (
    coalesce(heart_rate_bpm, 0) >= 0 and coalesce(blood_glucose_mg_dl, 0) >= 0 and
    coalesce(systolic_mmhg, 0) >= 0 and coalesce(diastolic_mmhg, 0) >= 0 and
    coalesce(pulse_bpm, 0) >= 0 and coalesce(weight_kg, 0) >= 0 and
    coalesce(bmi_value, 0) >= 0 and coalesce(body_fat_percent, 0) >= 0 and
    coalesce(skeletal_muscle_kg, 0) >= 0
  );

alter table public.lifestyle_nutrition
  add constraint lifestyle_nutrition_source_check check (source in ('manual', 'samsung_health', 'legacy')),
  add constraint lifestyle_nutrition_nonnegative_check check (
    coalesce(calories, 0) >= 0 and coalesce(total_fat, 0) >= 0 and
    coalesce(saturated_fat, 0) >= 0 and coalesce(polyunsaturated_fat, 0) >= 0 and
    coalesce(monounsaturated_fat, 0) >= 0 and coalesce(trans_fat, 0) >= 0 and
    coalesce(carbohydrate, 0) >= 0 and coalesce(dietary_fiber, 0) >= 0 and
    coalesce(sugar, 0) >= 0 and coalesce(protein, 0) >= 0 and
    coalesce(cholesterol, 0) >= 0 and coalesce(sodium, 0) >= 0 and
    coalesce(potassium, 0) >= 0 and coalesce(vitamin_a, 0) >= 0 and
    coalesce(vitamin_c, 0) >= 0 and coalesce(calcium, 0) >= 0 and coalesce(iron, 0) >= 0
  );

alter table public.lifestyle_water_intake
  add constraint lifestyle_water_intake_amount_check check (amount_ml > 0),
  add constraint lifestyle_water_intake_source_check check (source in ('manual', 'samsung_health', 'legacy'));

alter table public.lifestyle_sleep
  add constraint lifestyle_sleep_range_check check (end_at > start_at),
  add constraint lifestyle_sleep_nonnegative_check check (
    total_sleep_minutes >= 0 and coalesce(awake_minutes, 0) >= 0 and
    coalesce(deep_sleep_minutes, 0) >= 0 and coalesce(light_sleep_minutes, 0) >= 0 and
    coalesce(rem_sleep_minutes, 0) >= 0 and coalesce(sleep_score, 0) >= 0
  ),
  add constraint lifestyle_sleep_source_check check (source in ('manual', 'samsung_health', 'legacy'));

-- FK와 주요 조회 경로 인덱스
create index if not exists idx_chat_sessions_user_last_message on public.chat_sessions (user_id, last_message_at desc);
create index if not exists idx_chat_messages_session_order on public.chat_messages (session_id, message_order);
create index if not exists idx_health_checkup_records_user_date on public.health_checkup_records (user_id, measured_at desc);
create index if not exists idx_health_checkup_results_record on public.health_checkup_results (record_id);
create index if not exists idx_health_checkup_results_item on public.health_checkup_results (item_code);
create index if not exists idx_user_terms_consents_user_time on public.user_terms_consents (user_id, occurred_at desc);
create index if not exists idx_user_terms_consents_terms on public.user_terms_consents (terms_id);
create index if not exists idx_ocr_jobs_user_created on public.ocr_jobs (user_id, created_at desc);
create index if not exists idx_ocr_correction_logs_job on public.ocr_correction_logs (job_id);
create index if not exists idx_health_data_connections_user on public.health_data_connections (user_id);
create index if not exists idx_health_sync_runs_connection_started on public.health_sync_runs (connection_id, started_at desc);
create index if not exists idx_lifestyle_activity_user_date on public.lifestyle_activity (user_id, record_date desc);
create index if not exists idx_lifestyle_exercise_user_start on public.lifestyle_exercise (user_id, start_at desc);
create index if not exists idx_lifestyle_bio_user_type_time on public.lifestyle_bio (user_id, bio_type, measured_at desc);
create index if not exists idx_lifestyle_nutrition_user_time on public.lifestyle_nutrition (user_id, consumed_at desc);
create index if not exists idx_lifestyle_water_user_time on public.lifestyle_water_intake (user_id, consumed_at desc);
create index if not exists idx_lifestyle_sleep_user_start on public.lifestyle_sleep (user_id, start_at desc);
create index if not exists idx_daily_health_briefings_user_date on public.daily_health_briefings (user_id, briefing_date desc);
create index if not exists idx_health_alerts_user_status on public.health_alerts (user_id, status, detected_at desc);
create index if not exists idx_user_medications_user_status on public.user_medications (user_id, status);
create index if not exists idx_medication_schedules_medication on public.medication_schedules (medication_id);
create index if not exists idx_medication_intakes_user_schedule on public.medication_intakes (user_id, scheduled_at desc);
create index if not exists idx_medication_intakes_medication on public.medication_intakes (medication_id);
create index if not exists idx_notifications_user_schedule on public.notifications (user_id, scheduled_at desc);
create index if not exists idx_user_missions_user_date on public.user_missions (user_id, mission_date desc);
create index if not exists idx_mission_progress_events_mission on public.mission_progress_events (user_mission_id);
create index if not exists idx_mission_feedback_user on public.mission_feedback (user_id, created_at desc);
create index if not exists idx_coin_ledger_user_time on public.coin_ledger (user_id, created_at desc);
create index if not exists idx_shop_purchases_user on public.shop_purchases (user_id, created_at desc);
create index if not exists idx_user_inventory_user_status on public.user_inventory (user_id, status);
create unique index if not exists uq_user_inventory_owned_item on public.user_inventory (user_id, item_id) where status = 'owned';
create index if not exists idx_equipped_items_user on public.equipped_items (user_id);
create index if not exists idx_chat_message_citations_message on public.chat_message_citations (message_id);
create index if not exists idx_chat_suggested_actions_message on public.chat_suggested_actions (message_id);
create index if not exists idx_chat_suggested_actions_pending_expiry on public.chat_suggested_actions (expires_at) where status = 'pending';

-- updated_at을 일관되게 갱신한다.
create or replace function private.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function private.set_updated_at() from public, anon, authenticated;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'users', 'chat_sessions', 'master_checkup_item', 'health_checkup_records',
    'lifestyle_activity', 'lifestyle_exercise', 'lifestyle_bio', 'lifestyle_nutrition',
    'lifestyle_water_intake', 'lifestyle_sleep', 'ocr_jobs', 'health_data_connections',
    'user_home_modules', 'daily_health_briefings', 'health_alerts', 'user_medications',
    'medication_schedules', 'medication_intakes', 'notifications', 'user_missions',
    'shop_items'
  ]
  loop
    execute format('drop trigger if exists trg_%I_updated_at on public.%I', table_name, table_name);
    execute format(
      'create trigger trg_%I_updated_at before update on public.%I for each row execute function private.set_updated_at()',
      table_name,
      table_name
    );
  end loop;
end;
$$;

-- public 스키마의 모든 업무 테이블은 RLS를 사용한다.
do $$
declare
  table_name text;
begin
  for table_name in
    select cls.relname
    from pg_catalog.pg_class as cls
    join pg_catalog.pg_namespace as ns on ns.oid = cls.relnamespace
    where ns.nspname = 'public' and cls.relkind in ('r', 'p')
  loop
    execute format('alter table public.%I enable row level security', table_name);
  end loop;
end;
$$;

alter table private.device_tokens enable row level security;

-- 기존의 무제한 활동 INSERT 정책을 제거한다.
drop policy if exists "Enable insert for authenticated users only" on public.lifestyle_activity;

-- user_id를 직접 가진 테이블의 본인 조회 정책
do $$
declare
  table_name text;
  policy_name text;
begin
  foreach table_name in array array[
    'users', 'user_terms_consents', 'ocr_jobs', 'health_checkup_records',
    'health_data_connections', 'lifestyle_activity', 'lifestyle_exercise',
    'lifestyle_bio', 'lifestyle_nutrition', 'lifestyle_water_intake', 'lifestyle_sleep',
    'user_home_modules', 'daily_health_briefings', 'health_alerts', 'user_medications',
    'medication_intakes', 'notifications', 'user_missions', 'mission_feedback',
    'coin_ledger', 'shop_purchases', 'user_inventory', 'equipped_items'
  ]
  loop
    policy_name := table_name || '_select_own_v1';
    execute format('drop policy if exists %I on public.%I', policy_name, table_name);
    execute format(
      'create policy %I on public.%I for select to authenticated using ((select auth.uid()) = user_id)',
      policy_name,
      table_name
    );
  end loop;
end;
$$;

-- 사용자 프로필과 기존 상담 기능은 안전한 직접 쓰기를 유지한다.
drop policy if exists users_insert_own_v1 on public.users;
create policy users_insert_own_v1 on public.users for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists users_update_own_v1 on public.users;
create policy users_update_own_v1 on public.users for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists chat_sessions_select_own_v1 on public.chat_sessions;
create policy chat_sessions_select_own_v1 on public.chat_sessions for select to authenticated
using ((select auth.uid()) = user_id);
drop policy if exists chat_sessions_insert_own_v1 on public.chat_sessions;
create policy chat_sessions_insert_own_v1 on public.chat_sessions for insert to authenticated
with check ((select auth.uid()) = user_id);
drop policy if exists chat_sessions_update_own_v1 on public.chat_sessions;
create policy chat_sessions_update_own_v1 on public.chat_sessions for update to authenticated
using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists chat_sessions_delete_own_v1 on public.chat_sessions;
create policy chat_sessions_delete_own_v1 on public.chat_sessions for delete to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists chat_messages_select_own_v1 on public.chat_messages;
create policy chat_messages_select_own_v1 on public.chat_messages for select to authenticated
using (exists (
  select 1 from public.chat_sessions as session
  where session.session_id = chat_messages.session_id and session.user_id = (select auth.uid())
));
drop policy if exists chat_messages_insert_own_v1 on public.chat_messages;
create policy chat_messages_insert_own_v1 on public.chat_messages for insert to authenticated
with check (exists (
  select 1 from public.chat_sessions as session
  where session.session_id = chat_messages.session_id and session.user_id = (select auth.uid())
));

-- 기존 검진 등록 흐름의 본인 INSERT 정책을 보존한다.
drop policy if exists health_checkup_records_insert_own_v1 on public.health_checkup_records;
create policy health_checkup_records_insert_own_v1 on public.health_checkup_records for insert to authenticated
with check ((select auth.uid()) = user_id);
drop policy if exists health_checkup_results_select_own_v1 on public.health_checkup_results;
create policy health_checkup_results_select_own_v1 on public.health_checkup_results for select to authenticated
using (exists (
  select 1 from public.health_checkup_records as record
  where record.record_id = health_checkup_results.record_id and record.user_id = (select auth.uid())
));
drop policy if exists health_checkup_results_insert_own_v1 on public.health_checkup_results;
create policy health_checkup_results_insert_own_v1 on public.health_checkup_results for insert to authenticated
with check (exists (
  select 1 from public.health_checkup_records as record
  where record.record_id = health_checkup_results.record_id and record.user_id = (select auth.uid())
));

-- 자식 테이블의 조회 정책은 부모 행 소유권으로 판단한다.
drop policy if exists ocr_correction_logs_select_own_v1 on public.ocr_correction_logs;
create policy ocr_correction_logs_select_own_v1 on public.ocr_correction_logs for select to authenticated
using (exists (select 1 from public.ocr_jobs as job where job.job_id = ocr_correction_logs.job_id and job.user_id = (select auth.uid())));

drop policy if exists health_sync_runs_select_own_v1 on public.health_sync_runs;
create policy health_sync_runs_select_own_v1 on public.health_sync_runs for select to authenticated
using (exists (select 1 from public.health_data_connections as connection where connection.connection_id = health_sync_runs.connection_id and connection.user_id = (select auth.uid())));

drop policy if exists medication_schedules_select_own_v1 on public.medication_schedules;
create policy medication_schedules_select_own_v1 on public.medication_schedules for select to authenticated
using (exists (select 1 from public.user_medications as medication where medication.medication_id = medication_schedules.medication_id and medication.user_id = (select auth.uid())));

drop policy if exists medication_ocr_results_select_own_v1 on public.medication_ocr_results;
create policy medication_ocr_results_select_own_v1 on public.medication_ocr_results for select to authenticated
using (exists (select 1 from public.ocr_jobs as job where job.job_id = medication_ocr_results.ocr_job_id and job.user_id = (select auth.uid())));

drop policy if exists mission_progress_events_select_own_v1 on public.mission_progress_events;
create policy mission_progress_events_select_own_v1 on public.mission_progress_events for select to authenticated
using (exists (select 1 from public.user_missions as mission where mission.user_mission_id = mission_progress_events.user_mission_id and mission.user_id = (select auth.uid())));

drop policy if exists chat_message_citations_select_own_v1 on public.chat_message_citations;
create policy chat_message_citations_select_own_v1 on public.chat_message_citations for select to authenticated
using (exists (
  select 1 from public.chat_messages as message
  join public.chat_sessions as session on session.session_id = message.session_id
  where message.message_id = chat_message_citations.message_id and session.user_id = (select auth.uid())
));

drop policy if exists chat_suggested_actions_select_own_v1 on public.chat_suggested_actions;
create policy chat_suggested_actions_select_own_v1 on public.chat_suggested_actions for select to authenticated
using (exists (
  select 1 from public.chat_messages as message
  join public.chat_sessions as session on session.session_id = message.session_id
  where message.message_id = chat_suggested_actions.message_id and session.user_id = (select auth.uid())
));

-- 공용 기준 데이터는 로그인 사용자에게 읽기만 허용한다.
do $$
declare
  table_name text;
  policy_name text;
begin
  foreach table_name in array array[
    'terms', 'master_checkup_item', 'health_metric_policies', 'mission_catalog',
    'mission_rules', 'shop_items', 'medical_term', 'medical_term_alias',
    'medical_term_alias_initial'
  ]
  loop
    policy_name := table_name || '_select_authenticated_v1';
    execute format('drop policy if exists %I on public.%I', policy_name, table_name);
    execute format('create policy %I on public.%I for select to authenticated using (true)', policy_name, table_name);
  end loop;
end;
$$;

-- Data API 권한과 RLS는 별개이므로 역할별 권한을 명시한다.
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
grant select on all tables in schema public to authenticated;
grant insert, update on public.users to authenticated;
grant insert, update, delete on public.chat_sessions to authenticated;
grant insert on public.chat_messages to authenticated;
grant insert on public.health_checkup_records, public.health_checkup_results to authenticated;
grant usage, select on all sequences in schema public to authenticated;

grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant usage on schema private to service_role;
grant all on private.device_tokens to service_role;

revoke all on private.device_tokens from anon, authenticated;

commit;
