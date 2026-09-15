-- 사용자 본인 생활습관 데이터 조회 권한과 조회 인덱스
-- 작성자: 고수연

CREATE INDEX IF NOT EXISTS lifestyle_activity_user_record_date_idx
    ON public.lifestyle_activity (user_id, record_date DESC);
CREATE INDEX IF NOT EXISTS lifestyle_bio_user_type_measured_at_idx
    ON public.lifestyle_bio (user_id, bio_type, measured_at DESC);
CREATE INDEX IF NOT EXISTS lifestyle_exercise_user_record_date_idx
    ON public.lifestyle_exercise (user_id, record_date DESC);
CREATE INDEX IF NOT EXISTS lifestyle_nutrition_user_type_consumed_at_idx
    ON public.lifestyle_nutrition (user_id, nutrition_type, consumed_at DESC);

ALTER TABLE public.lifestyle_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lifestyle_bio ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lifestyle_exercise ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lifestyle_nutrition ENABLE ROW LEVEL SECURITY;


DROP POLICY IF EXISTS "Enable users to view their own data only"
    ON public.lifestyle_activity;
DROP POLICY IF EXISTS lifestyle_activity_select_own ON public.lifestyle_activity;
CREATE POLICY lifestyle_activity_select_own
    ON public.lifestyle_activity
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Enable users to view their own data only"
    ON public.lifestyle_bio;
DROP POLICY IF EXISTS lifestyle_bio_select_own ON public.lifestyle_bio;
CREATE POLICY lifestyle_bio_select_own
    ON public.lifestyle_bio
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Enable users to view their own data only"
    ON public.lifestyle_exercise;
DROP POLICY IF EXISTS lifestyle_exercise_select_own ON public.lifestyle_exercise;
CREATE POLICY lifestyle_exercise_select_own
    ON public.lifestyle_exercise
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Enable users to view their own data only"
    ON public.lifestyle_nutrition;
DROP POLICY IF EXISTS lifestyle_nutrition_select_own ON public.lifestyle_nutrition;
CREATE POLICY lifestyle_nutrition_select_own
    ON public.lifestyle_nutrition
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

-- 개인 생활습관 기록은 다른 개인정보 테이블(004)과 같은 기준으로 로그인 사용자에게만 SELECT를 허용한다.
REVOKE ALL ON public.lifestyle_activity,
    public.lifestyle_bio,
    public.lifestyle_exercise,
    public.lifestyle_nutrition
    FROM anon, authenticated;
GRANT SELECT ON public.lifestyle_activity,
    public.lifestyle_bio,
    public.lifestyle_exercise,
    public.lifestyle_nutrition
    TO authenticated;

-- 주의: lifestyle_activity에는 대시보드에서 추가된 INSERT 정책. 데이터 연동을 기반으로 데이터 적재가 되어야하므로 테스트용으로 권한을 하나 열어두었으나, 현재는 동작하지 않는다.
-- 기기 연동 적재 경로가 이 정책에 의존한다면 소유 검증(WITH CHECK ((SELECT auth.uid()) = user_id))과 함께 GRANT INSERT를 별도 마이그레이션에서 명시적으로 복원해야 한다.
