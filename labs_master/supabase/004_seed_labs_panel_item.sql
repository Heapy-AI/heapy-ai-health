-- Supabase SQL Editor 실행 순서: 4/5
-- CBC 등 검사 패널과 개별 검사 관계 39개
BEGIN;

WITH panel_data (
    panel_item_code, included_item_code, display_order, requirement_type
) AS (
    VALUES
    ('PULMONARY_FUNCTION', 'FEV1', 1, 'REQUIRED'),
    ('PULMONARY_FUNCTION', 'FVC', 2, 'REQUIRED'),
    ('PULMONARY_FUNCTION', 'FEV1_FVC_RATIO', 3, 'REQUIRED'),
    ('BONE_DENSITY', 'BONE_DENSITY_T_SCORE', 1, 'REQUIRED'),
    ('BONE_DENSITY', 'BONE_DENSITY_Z_SCORE', 2, 'OPTIONAL'),
    ('CBC_PANEL', 'HEMOGLOBIN', 1, 'REQUIRED'),
    ('CBC_PANEL', 'HEMATOCRIT', 2, 'REQUIRED'),
    ('CBC_PANEL', 'WBC_COUNT', 3, 'REQUIRED'),
    ('CBC_PANEL', 'RBC_COUNT', 4, 'REQUIRED'),
    ('CBC_PANEL', 'PLATELET_COUNT', 5, 'REQUIRED'),
    ('CBC_PANEL', 'MCV', 6, 'REQUIRED'),
    ('CBC_PANEL', 'MCH', 7, 'REQUIRED'),
    ('CBC_PANEL', 'MCHC', 8, 'REQUIRED'),
    ('CBC_PANEL', 'RDW', 9, 'OPTIONAL'),
    ('CBC_PANEL', 'MPV', 10, 'OPTIONAL'),
    ('LIVER_FUNCTION_PANEL', 'AST', 1, 'REQUIRED'),
    ('LIVER_FUNCTION_PANEL', 'ALT', 2, 'REQUIRED'),
    ('LIVER_FUNCTION_PANEL', 'GAMMA_GTP', 3, 'OPTIONAL'),
    ('LIVER_FUNCTION_PANEL', 'ALP', 4, 'OPTIONAL'),
    ('LIVER_FUNCTION_PANEL', 'TOTAL_BILIRUBIN', 5, 'OPTIONAL'),
    ('LIVER_FUNCTION_PANEL', 'TOTAL_PROTEIN', 6, 'OPTIONAL'),
    ('LIVER_FUNCTION_PANEL', 'ALBUMIN', 7, 'OPTIONAL'),
    ('LIPID_PANEL', 'TOTAL_CHOLESTEROL', 1, 'REQUIRED'),
    ('LIPID_PANEL', 'TRIGLYCERIDES', 2, 'REQUIRED'),
    ('LIPID_PANEL', 'HDL_CHOLESTEROL', 3, 'REQUIRED'),
    ('LIPID_PANEL', 'LDL_CHOLESTEROL', 4, 'REQUIRED'),
    ('THYROID_FUNCTION_PANEL', 'TSH', 1, 'REQUIRED'),
    ('THYROID_FUNCTION_PANEL', 'FREE_T4', 2, 'REQUIRED'),
    ('THYROID_FUNCTION_PANEL', 'T3', 3, 'OPTIONAL'),
    ('URINALYSIS_PANEL', 'URINE_PH', 1, 'REQUIRED'),
    ('URINALYSIS_PANEL', 'URINE_PROTEIN', 2, 'REQUIRED'),
    ('URINALYSIS_PANEL', 'URINE_GLUCOSE', 3, 'REQUIRED'),
    ('URINALYSIS_PANEL', 'URINE_OCCULT_BLOOD', 4, 'REQUIRED'),
    ('URINALYSIS_PANEL', 'URINE_SPECIFIC_GRAVITY', 5, 'REQUIRED'),
    ('URINALYSIS_PANEL', 'URINE_LEUKOCYTE', 6, 'OPTIONAL'),
    ('URINALYSIS_PANEL', 'URINE_NITRITE', 7, 'OPTIONAL'),
    ('URINALYSIS_PANEL', 'URINE_KETONE', 8, 'OPTIONAL'),
    ('URINALYSIS_PANEL', 'URINE_BILIRUBIN', 9, 'OPTIONAL'),
    ('URINALYSIS_PANEL', 'URINE_UROBILINOGEN', 10, 'OPTIONAL')
)
INSERT INTO labs_panel_item (
    panel_item_id, included_item_id, display_order, requirement_type
)
SELECT
    panel.item_id,
    included.item_id,
    panel_data.display_order::SMALLINT,
    panel_data.requirement_type
FROM panel_data
JOIN labs_item_master AS panel
    ON panel.item_code = panel_data.panel_item_code
JOIN labs_item_master AS included
    ON included.item_code = panel_data.included_item_code
ON CONFLICT (panel_item_id, included_item_id)
DO UPDATE SET
    display_order = EXCLUDED.display_order,
    requirement_type = EXCLUDED.requirement_type;

COMMIT;
