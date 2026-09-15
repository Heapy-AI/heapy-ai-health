-- 생활건강 전용 수면·수분 데이터 조회 권한
-- 로그인 사용자는 자신의 행만 조회한다.

CREATE INDEX IF NOT EXISTS lifestyle_sleep_user_start_at_idx
    ON public.lifestyle_sleep (user_id, start_at DESC);
CREATE INDEX IF NOT EXISTS lifestyle_water_intake_user_consumed_at_idx
    ON public.lifestyle_water_intake (user_id, consumed_at DESC);

ALTER TABLE public.lifestyle_sleep ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lifestyle_water_intake ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lifestyle_sleep_select_own
    ON public.lifestyle_sleep;
CREATE POLICY lifestyle_sleep_select_own
    ON public.lifestyle_sleep
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS lifestyle_water_intake_select_own
    ON public.lifestyle_water_intake;
CREATE POLICY lifestyle_water_intake_select_own
    ON public.lifestyle_water_intake
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

REVOKE ALL ON public.lifestyle_sleep, public.lifestyle_water_intake
    FROM anon, authenticated;
GRANT SELECT ON public.lifestyle_sleep, public.lifestyle_water_intake
    TO authenticated;
