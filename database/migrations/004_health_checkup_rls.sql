-- 사용자 본인 건강검진 데이터 조회 권한과 조회 인덱스
-- 작성자: 김진우

CREATE INDEX IF NOT EXISTS health_checkup_records_user_measured_at_idx
    ON public.health_checkup_records (user_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS health_checkup_results_record_item_idx
    ON public.health_checkup_results (record_id, item_code);

DROP POLICY IF EXISTS health_checkup_records_select_own
    ON public.health_checkup_records;
CREATE POLICY health_checkup_records_select_own
    ON public.health_checkup_records
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS health_checkup_results_select_own
    ON public.health_checkup_results;
CREATE POLICY health_checkup_results_select_own
    ON public.health_checkup_results
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM public.health_checkup_records AS record
            WHERE record.record_id = health_checkup_results.record_id
              AND record.user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS master_checkup_item_select_authenticated
    ON public.master_checkup_item;
CREATE POLICY master_checkup_item_select_authenticated
    ON public.master_checkup_item
    FOR SELECT
    TO authenticated
    USING (true);

REVOKE ALL ON public.health_checkup_records,
    public.health_checkup_results,
    public.master_checkup_item
    FROM anon, authenticated;
GRANT SELECT ON public.health_checkup_records,
    public.health_checkup_results,
    public.master_checkup_item
    TO authenticated;
