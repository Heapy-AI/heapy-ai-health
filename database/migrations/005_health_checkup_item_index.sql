-- 검사항목 코드 필터와 외래키 검사를 위한 단독 인덱스
-- 작성자: 김진우

CREATE INDEX IF NOT EXISTS health_checkup_results_item_code_idx
    ON public.health_checkup_results (item_code);
