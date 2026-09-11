-- Advisor 결과에 따라 기존·v1 중복 정책과 인덱스를 정리한다.
-- 작성자: 김진우

begin;

drop policy if exists users_select_own_v1 on public.users;
drop policy if exists users_update_own_v1 on public.users;

drop policy if exists chat_sessions_select_own_v1 on public.chat_sessions;
drop policy if exists chat_sessions_insert_own_v1 on public.chat_sessions;
drop policy if exists chat_sessions_update_own_v1 on public.chat_sessions;
drop policy if exists chat_sessions_delete_own_v1 on public.chat_sessions;
drop policy if exists chat_messages_select_own_v1 on public.chat_messages;
drop policy if exists chat_messages_insert_own_v1 on public.chat_messages;

drop policy if exists health_checkup_records_select_own_v1 on public.health_checkup_records;
drop policy if exists health_checkup_records_insert_own_v1 on public.health_checkup_records;
drop policy if exists health_checkup_results_select_own_v1 on public.health_checkup_results;
drop policy if exists health_checkup_results_insert_own_v1 on public.health_checkup_results;

drop policy if exists lifestyle_activity_select_own_v1 on public.lifestyle_activity;
drop policy if exists lifestyle_exercise_select_own_v1 on public.lifestyle_exercise;
drop policy if exists lifestyle_bio_select_own_v1 on public.lifestyle_bio;
drop policy if exists lifestyle_nutrition_select_own_v1 on public.lifestyle_nutrition;

-- 기존 정책이 활성 행만 공개하므로 더 넓은 v1 공용 정책을 제거한다.
drop policy if exists master_checkup_item_select_authenticated_v1 on public.master_checkup_item;
drop policy if exists medical_term_select_authenticated_v1 on public.medical_term;
drop policy if exists medical_term_alias_select_authenticated_v1 on public.medical_term_alias;
drop policy if exists medical_term_alias_initial_select_authenticated_v1 on public.medical_term_alias_initial;

drop index if exists public.idx_chat_messages_session_order;
drop index if exists public.idx_health_checkup_records_user_date;
drop index if exists public.idx_health_checkup_results_item;

commit;
