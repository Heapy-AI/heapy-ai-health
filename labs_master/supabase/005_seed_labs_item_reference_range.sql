-- Supabase SQL Editor 실행 순서: 5/5
-- 2026 국가 일반건강검진의 출처 확인 가능한 정상 A 참고기준 14개
BEGIN;

WITH reference_data (
    item_code, applies_to_sex, age_from, age_to, minimum_value, maximum_value,
    reference_text, institution_name, valid_from, valid_to, is_active
) AS (
    VALUES
    ('HEMOGLOBIN', 'MALE', NULL, NULL, '13.0', '16.5', '2026 국가 일반건강검진 정상 A: 남성 13.0~16.5 g/dL', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('HEMOGLOBIN', 'FEMALE', NULL, NULL, '12.0', '15.5', '2026 국가 일반건강검진 정상 A: 여성 12.0~15.5 g/dL', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('FASTING_GLUCOSE', 'ALL', NULL, NULL, NULL, NULL, '2026 국가 일반건강검진 정상 A: 100 mg/dL 미만', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('TOTAL_CHOLESTEROL', 'ALL', NULL, NULL, NULL, NULL, '2026 국가 일반건강검진 정상 A: 200 mg/dL 미만', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('HDL_CHOLESTEROL', 'ALL', NULL, NULL, NULL, NULL, '2026 국가 일반건강검진 정상 A: 60 mg/dL 이상', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('TRIGLYCERIDES', 'ALL', NULL, NULL, NULL, NULL, '2026 국가 일반건강검진 정상 A: 150 mg/dL 미만', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('LDL_CHOLESTEROL', 'ALL', NULL, NULL, NULL, NULL, '2026 국가 일반건강검진 정상 A: 130 mg/dL 미만', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('AST', 'ALL', NULL, NULL, NULL, '40.0', '2026 국가 일반건강검진 정상 A: 40 U/L 이하', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('ALT', 'ALL', NULL, NULL, NULL, '35.0', '2026 국가 일반건강검진 정상 A: 35 U/L 이하', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('GAMMA_GTP', 'MALE', NULL, NULL, '11.0', '63.0', '2026 국가 일반건강검진 정상 A: 남성 11~63 U/L', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('GAMMA_GTP', 'FEMALE', NULL, NULL, '8.0', '35.0', '2026 국가 일반건강검진 정상 A: 여성 8~35 U/L', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('SERUM_CREATININE', 'ALL', NULL, NULL, NULL, '1.5', '2026 국가 일반건강검진 정상 A: 1.5 mg/dL 이하', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('EGFR', 'ALL', NULL, NULL, '60.0', NULL, '2026 국가 일반건강검진 정상 A: 60 mL/min/1.73m2 이상', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE),
    ('URINE_PROTEIN', 'ALL', NULL, NULL, NULL, NULL, '2026 국가 일반건강검진 정상 A: 음성(-)', '보건복지부 국가 일반건강검진 기준', '2026-01-07', NULL, TRUE)
)
INSERT INTO labs_item_reference_range (
    item_id, applies_to_sex, age_from, age_to, minimum_value, maximum_value,
    reference_text, institution_name, valid_from, valid_to, is_active
)
SELECT
    item.item_id,
    reference_data.applies_to_sex,
    reference_data.age_from::SMALLINT,
    reference_data.age_to::SMALLINT,
    reference_data.minimum_value::NUMERIC(16, 4),
    reference_data.maximum_value::NUMERIC(16, 4),
    reference_data.reference_text,
    reference_data.institution_name,
    reference_data.valid_from::DATE,
    reference_data.valid_to::DATE,
    reference_data.is_active
FROM reference_data
JOIN labs_item_master AS item
    ON item.item_code = reference_data.item_code
ON CONFLICT ON CONSTRAINT uq_labs_item_reference_range
DO UPDATE SET
    is_active = EXCLUDED.is_active;

COMMIT;
