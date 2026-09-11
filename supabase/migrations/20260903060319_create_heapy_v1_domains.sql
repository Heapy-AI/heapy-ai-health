-- HEAPY v1 신규 도메인 테이블 생성
-- 작성자: 김진우

begin;

create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table public.terms (
  terms_id bigint generated always as identity primary key,
  terms_code text not null,
  version text not null,
  title text not null,
  content_url text not null,
  content_hash text not null,
  is_required boolean not null,
  effective_at timestamptz not null,
  retired_at timestamptz,
  created_at timestamptz not null default now(),
  constraint terms_code_version_uq unique (terms_code, version),
  constraint terms_period_check check (retired_at is null or retired_at > effective_at)
);

create table public.user_terms_consents (
  consent_id bigint generated always as identity primary key,
  user_id uuid not null references public.users(user_id) on delete cascade,
  terms_id bigint not null references public.terms(terms_id) on delete restrict,
  action text not null,
  consent_source text not null,
  idempotency_key uuid not null,
  occurred_at timestamptz not null default now(),
  constraint user_terms_consents_action_check check (action in ('consent', 'withdraw')),
  constraint user_terms_consents_idempotency_uq unique (user_id, idempotency_key)
);

create table public.ocr_jobs (
  job_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  document_type text not null,
  input_type text not null,
  status text not null default 'pending',
  page_count smallint,
  error_code text,
  error_message text,
  idempotency_key uuid not null,
  started_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ocr_jobs_document_type_check check (document_type in ('health_checkup', 'medication')),
  constraint ocr_jobs_input_type_check check (input_type in ('image', 'pdf')),
  constraint ocr_jobs_status_check check (status in ('pending', 'processing', 'review', 'confirmed', 'failed', 'expired')),
  constraint ocr_jobs_page_count_check check (page_count is null or page_count > 0),
  constraint ocr_jobs_idempotency_uq unique (user_id, idempotency_key)
);

create table public.ocr_correction_logs (
  correction_log_id bigint generated always as identity primary key,
  job_id uuid not null references public.ocr_jobs(job_id) on delete cascade,
  item_code text references public.master_checkup_item(item_code) on delete restrict,
  field_key text not null,
  original_value text,
  corrected_value text,
  correction_type text not null,
  created_at timestamptz not null default now(),
  constraint ocr_correction_logs_type_check check (correction_type in ('edit', 'add', 'remove'))
);

alter table public.health_checkup_records
  add constraint health_checkup_records_source_ocr_job_fkey
  foreign key (source_ocr_job_id) references public.ocr_jobs(job_id) on delete set null;

create table public.health_data_connections (
  connection_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  provider text not null default 'samsung_health',
  device_installation_id uuid not null,
  status text not null default 'connected',
  granted_data_types text[] not null default '{}'::text[],
  sdk_version text,
  last_permission_checked_at timestamptz,
  last_synced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint health_data_connections_provider_check check (provider = 'samsung_health'),
  constraint health_data_connections_status_check check (status in ('connected', 'disconnected', 'permission_required')),
  constraint health_data_connections_device_uq unique (user_id, provider, device_installation_id)
);

create table public.health_sync_runs (
  sync_run_id uuid primary key default gen_random_uuid(),
  connection_id uuid not null references public.health_data_connections(connection_id) on delete cascade,
  idempotency_key uuid not null,
  sync_mode text not null,
  status text not null default 'running',
  requested_data_types text[] not null default '{}'::text[],
  cursor_state jsonb not null default '{}'::jsonb,
  received_count integer not null default 0,
  inserted_count integer not null default 0,
  updated_count integer not null default 0,
  skipped_count integer not null default 0,
  error_code text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint health_sync_runs_mode_check check (sync_mode in ('app_open', 'manual_refresh')),
  constraint health_sync_runs_status_check check (status in ('running', 'succeeded', 'failed')),
  constraint health_sync_runs_counts_check check (
    received_count >= 0 and inserted_count >= 0 and updated_count >= 0 and skipped_count >= 0
  ),
  constraint health_sync_runs_idempotency_uq unique (connection_id, idempotency_key)
);

alter table public.lifestyle_activity
  add constraint lifestyle_activity_sync_run_fkey
  foreign key (sync_run_id) references public.health_sync_runs(sync_run_id) on delete set null;
alter table public.lifestyle_exercise
  add constraint lifestyle_exercise_sync_run_fkey
  foreign key (sync_run_id) references public.health_sync_runs(sync_run_id) on delete set null;
alter table public.lifestyle_bio
  add constraint lifestyle_bio_sync_run_fkey
  foreign key (sync_run_id) references public.health_sync_runs(sync_run_id) on delete set null;
alter table public.lifestyle_nutrition
  add constraint lifestyle_nutrition_sync_run_fkey
  foreign key (sync_run_id) references public.health_sync_runs(sync_run_id) on delete set null;
alter table public.lifestyle_water_intake
  add constraint lifestyle_water_intake_sync_run_fkey
  foreign key (sync_run_id) references public.health_sync_runs(sync_run_id) on delete set null;
alter table public.lifestyle_sleep
  add constraint lifestyle_sleep_sync_run_fkey
  foreign key (sync_run_id) references public.health_sync_runs(sync_run_id) on delete set null;

create table public.user_home_modules (
  user_id uuid not null references public.users(user_id) on delete cascade,
  module_code text not null,
  is_visible boolean not null default true,
  display_order smallint not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, module_code),
  constraint user_home_modules_code_check check (module_code in ('briefing', 'alerts', 'medication', 'missions')),
  constraint user_home_modules_order_check check (display_order between 1 and 4),
  constraint user_home_modules_order_uq unique (user_id, display_order)
);

create table public.health_metric_policies (
  policy_id bigint generated always as identity primary key,
  metric_code text not null,
  version integer not null,
  window_days smallint not null,
  min_valid_days smallint not null,
  rule_config jsonb not null default '{}'::jsonb,
  effective_at timestamptz not null,
  retired_at timestamptz,
  created_at timestamptz not null default now(),
  constraint health_metric_policies_version_uq unique (metric_code, version),
  constraint health_metric_policies_days_check check (
    window_days > 0 and min_valid_days > 0 and min_valid_days <= window_days
  ),
  constraint health_metric_policies_period_check check (retired_at is null or retired_at > effective_at)
);

create table public.daily_health_briefings (
  briefing_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  briefing_date date not null,
  status text not null,
  headline text,
  body text,
  sections jsonb not null default '[]'::jsonb,
  evidence_snapshot jsonb not null default '{}'::jsonb,
  metric_policy_versions jsonb not null default '{}'::jsonb,
  model_name text,
  model_version text,
  prompt_version text,
  failure_code text,
  generated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint daily_health_briefings_status_check check (status in ('pending', 'generated', 'insufficient_data', 'failed')),
  constraint daily_health_briefings_user_date_uq unique (user_id, briefing_date)
);

create table public.health_alerts (
  alert_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  alert_type text not null,
  severity text not null,
  status text not null default 'active',
  title text not null,
  message text not null,
  evidence_snapshot jsonb not null default '{}'::jsonb,
  source_record_refs jsonb not null default '[]'::jsonb,
  policy_version integer not null,
  dedupe_key text not null,
  detected_at timestamptz not null default now(),
  acknowledged_at timestamptz,
  resolved_at timestamptz,
  expires_at timestamptz,
  purge_after timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint health_alerts_severity_check check (severity in ('info', 'warning', 'critical')),
  constraint health_alerts_status_check check (status in ('active', 'acknowledged', 'resolved', 'expired')),
  constraint health_alerts_dedupe_uq unique (user_id, dedupe_key, detected_at)
);

create table public.user_medications (
  medication_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  display_name text not null,
  dose_amount numeric(10,3),
  dose_unit text,
  dosage_text text not null,
  instructions text,
  start_date date not null,
  end_date date,
  status text not null default 'active',
  registration_source text not null default 'manual',
  source_ocr_job_id uuid references public.ocr_jobs(job_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_medications_period_check check (end_date is null or end_date >= start_date),
  constraint user_medications_status_check check (status in ('active', 'archived')),
  constraint user_medications_source_check check (registration_source in ('manual', 'ocr'))
);

create table public.medication_schedules (
  schedule_id uuid primary key default gen_random_uuid(),
  medication_id uuid not null references public.user_medications(medication_id) on delete cascade,
  scheduled_time time not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint medication_schedules_time_uq unique (medication_id, scheduled_time)
);

create table public.medication_intakes (
  intake_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  medication_id uuid not null references public.user_medications(medication_id) on delete restrict,
  schedule_id uuid references public.medication_schedules(schedule_id) on delete set null,
  scheduled_at timestamptz not null,
  medication_name_snapshot text not null,
  dosage_snapshot text not null,
  status text not null default 'pending',
  action_source text,
  acted_at timestamptz,
  missed_at timestamptz,
  idempotency_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint medication_intakes_status_check check (status in ('pending', 'taken', 'skipped', 'missed')),
  constraint medication_intakes_schedule_uq unique (medication_id, scheduled_at),
  constraint medication_intakes_idempotency_uq unique (user_id, idempotency_key)
);

create table public.medication_ocr_results (
  medication_ocr_result_id uuid primary key default gen_random_uuid(),
  ocr_job_id uuid not null references public.ocr_jobs(job_id) on delete cascade,
  item_order smallint not null,
  raw_name text,
  raw_dosage text,
  normalized_name text,
  normalized_dosage jsonb not null default '{}'::jsonb,
  confidence numeric(5,4),
  confirmed_data jsonb,
  confirmed_at timestamptz,
  medication_id uuid references public.user_medications(medication_id) on delete set null,
  created_at timestamptz not null default now(),
  constraint medication_ocr_results_order_check check (item_order > 0),
  constraint medication_ocr_results_confidence_check check (confidence is null or confidence between 0 and 1),
  constraint medication_ocr_results_order_uq unique (ocr_job_id, item_order)
);

create table private.device_tokens (
  device_token_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  device_identifier_hash text not null,
  platform text not null,
  push_token text not null,
  is_active boolean not null default true,
  last_seen_at timestamptz not null default now(),
  invalidated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint device_tokens_platform_check check (platform in ('android', 'ios')),
  constraint device_tokens_push_token_uq unique (push_token),
  constraint device_tokens_device_uq unique (user_id, device_identifier_hash, platform)
);

create table public.notifications (
  notification_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  notification_type text not null,
  target_type text not null,
  target_id uuid,
  title text not null,
  body text not null,
  status text not null default 'scheduled',
  scheduled_at timestamptz not null,
  sent_at timestamptz,
  opened_at timestamptz,
  actioned_at timestamptz,
  provider_message_id text,
  failure_code text,
  idempotency_key text not null,
  purge_after timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint notifications_status_check check (status in ('scheduled', 'sent', 'opened', 'actioned', 'failed', 'cancelled')),
  constraint notifications_idempotency_uq unique (user_id, idempotency_key)
);

create table public.mission_catalog (
  mission_catalog_id bigint generated always as identity primary key,
  mission_code text not null,
  version integer not null,
  mission_type text not null,
  title text not null,
  description text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  constraint mission_catalog_version_uq unique (mission_code, version)
);

create table public.mission_rules (
  mission_rule_id bigint generated always as identity primary key,
  mission_code text not null,
  version integer not null,
  required_data jsonb not null default '[]'::jsonb,
  condition jsonb not null default '{}'::jsonb,
  exclusions jsonb not null default '[]'::jsonb,
  completion_rule jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint mission_rules_version_uq unique (mission_code, version)
);

create table public.user_missions (
  user_mission_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  mission_code text not null,
  catalog_version integer not null,
  rule_version integer not null,
  source text not null,
  target_value jsonb not null default '{}'::jsonb,
  progress_value jsonb not null default '{}'::jsonb,
  status text not null default 'active',
  mission_date date not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  idempotency_key uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_missions_status_check check (status in ('active', 'completed', 'failed', 'abandoned')),
  constraint user_missions_period_check check (ends_at > starts_at),
  constraint user_missions_idempotency_uq unique (user_id, idempotency_key)
);

create table public.mission_progress_events (
  progress_event_id bigint generated always as identity primary key,
  user_mission_id uuid not null references public.user_missions(user_mission_id) on delete cascade,
  source_type text not null,
  source_record_id text not null,
  source_version text not null,
  contribution numeric not null,
  created_at timestamptz not null default now(),
  constraint mission_progress_source_uq unique (user_mission_id, source_type, source_record_id, source_version)
);

create table public.mission_feedback (
  feedback_id bigint generated always as identity primary key,
  user_mission_id uuid not null references public.user_missions(user_mission_id) on delete cascade,
  user_id uuid not null references public.users(user_id) on delete cascade,
  event_type text not null,
  reason text,
  created_at timestamptz not null default now(),
  constraint mission_feedback_event_check check (event_type in ('completed', 'failed', 'abandoned', 'rejected'))
);

create table public.coin_ledger (
  ledger_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  entry_type text not null,
  amount integer not null,
  reference_type text not null,
  reference_id uuid not null,
  idempotency_key uuid not null,
  created_at timestamptz not null default now(),
  constraint coin_ledger_amount_check check (amount <> 0),
  constraint coin_ledger_idempotency_uq unique (user_id, idempotency_key)
);

create table public.shop_items (
  item_id uuid primary key default gen_random_uuid(),
  item_code text not null unique,
  slot text not null,
  name text not null,
  current_price integer not null,
  sale_status text not null default 'on_sale',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint shop_items_price_check check (current_price >= 0),
  constraint shop_items_status_check check (sale_status in ('on_sale', 'off_sale'))
);

create table public.shop_purchases (
  purchase_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  item_id uuid not null references public.shop_items(item_id) on delete restrict,
  debit_ledger_id uuid not null references public.coin_ledger(ledger_id) on delete restrict,
  status text not null default 'completed',
  cancellable_until timestamptz not null,
  idempotency_key uuid not null,
  created_at timestamptz not null default now(),
  cancelled_at timestamptz,
  refund_ledger_id uuid references public.coin_ledger(ledger_id) on delete restrict,
  constraint shop_purchases_status_check check (status in ('completed', 'cancelled')),
  constraint shop_purchases_idempotency_uq unique (user_id, idempotency_key)
);

create table public.user_inventory (
  inventory_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  item_id uuid not null references public.shop_items(item_id) on delete restrict,
  purchase_id uuid not null references public.shop_purchases(purchase_id) on delete restrict,
  status text not null default 'owned',
  acquired_at timestamptz not null default now(),
  revoked_at timestamptz,
  constraint user_inventory_status_check check (status in ('owned', 'revoked')),
  constraint user_inventory_purchase_uq unique (purchase_id)
);

create table public.equipped_items (
  equipped_item_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(user_id) on delete cascade,
  slot text not null,
  inventory_id uuid not null references public.user_inventory(inventory_id) on delete restrict,
  equipped_at timestamptz not null default now(),
  constraint equipped_items_slot_uq unique (user_id, slot),
  constraint equipped_items_inventory_uq unique (inventory_id)
);

create table public.chat_message_citations (
  citation_id bigint generated always as identity primary key,
  message_id uuid not null references public.chat_messages(message_id) on delete cascade,
  display_order smallint not null,
  source_type text not null,
  source_title text,
  source_url text,
  document_id text,
  excerpt text,
  constraint chat_message_citations_order_check check (display_order > 0),
  constraint chat_message_citations_source_check check (source_url is not null or document_id is not null),
  constraint chat_message_citations_order_uq unique (message_id, display_order)
);

create table public.chat_suggested_actions (
  suggested_action_id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.chat_messages(message_id) on delete cascade,
  title text not null,
  description text,
  mission_code text not null,
  status text not null default 'pending',
  expires_at timestamptz not null,
  accepted_user_mission_id uuid references public.user_missions(user_mission_id) on delete set null,
  created_at timestamptz not null default now(),
  accepted_at timestamptz,
  constraint chat_suggested_actions_status_check check (status in ('pending', 'accepted', 'expired', 'dismissed'))
);

create table public.rag_chunks (
  chunk_id uuid primary key default gen_random_uuid(),
  document_id text not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector,
  created_at timestamptz not null default now()
);

commit;
