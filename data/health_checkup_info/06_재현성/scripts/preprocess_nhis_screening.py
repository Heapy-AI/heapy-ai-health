#!/usr/bin/env python3
"""Build user-centred app datasets from NHIS screening reference files.

The inputs have three different roles and must not be blended:

* the NHIS cohort table is a public benchmark, never a personal diagnosis;
* NHIS claim-item codes are internal billing/reference codes, not result values;
* the MOHW result notice describes the personal fields shown to a screened user.

Blank cohort counts are preserved as null because the official API states that a
blank means that data does not exist. Outcome counts are also marked
non-exclusive; the source allows one screened person to appear in several result
categories.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import pdfplumber
except ImportError as exc:  # pragma: no cover - exercised by CLI users
    raise SystemExit(
        "pdfplumber is required. Install requirements-vdb.txt before running."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT.parent
NHIS_RAW_DIR = ROOT / "storage/source_document/nhis_screening/raw"
MOHW_RAW_DIR = ROOT / "storage/source_document/mohw_screening/raw"
OUTPUT_DIR = ROOT / "storage/source_document/nhis_screening/normalized"

DOWNLOAD_CLAIM = Path(
    PACKAGE_ROOT / "05_원본근거/NHIS/2024-07-31__NHIS__screening-claim-item-codes.csv"
)
DOWNLOAD_STATS = Path(
    PACKAGE_ROOT / "05_원본근거/NHIS/2023-12-31__NHIS__screening-statistics-by-job-sex-age.csv"
)
DOWNLOAD_FORM = Path(
    PACKAGE_ROOT / "05_원본근거/보건복지부/2026-01-07__MOHW-2026-6__appendix-6-result-notice.pdf"
)

RAW_CLAIM = NHIS_RAW_DIR / "2024-07-31__NHIS__screening-claim-item-codes.csv"
RAW_STATS = NHIS_RAW_DIR / "2023-12-31__NHIS__screening-statistics-by-job-sex-age.csv"
RAW_FORM = MOHW_RAW_DIR / "2026-01-07__MOHW-2026-6__appendix-6-result-notice.pdf"

CLAIM_HISTORY_CSV = "2024-07-31__NHIS__screening-claim-item-code-history.csv"
CLAIM_CURRENT_CSV = "2024-07-31__NHIS__screening-claim-item-code-current.csv"
COHORT_SUMMARY_CSV = "2023-12-31__NHIS__screening-cohort-summary.csv"
METRICS_LONG_CSV = "2023-12-31__NHIS__screening-metrics-long.csv"
METRIC_DICTIONARY_CSV = "2023-12-31__NHIS__screening-metric-dictionary.csv"
RESULT_FORM_FIELDS_CSV = "2026-01-07__MOHW-2026-6__result-form-field-dictionary.csv"
DATA_ROLE_CSV = "2026-07-16__health-app-source-role-matrix.csv"
DATA_CONTRACT_JSON = "2026-07-16__health-app-user-data-contract.json"
QUALITY_JSON = "2026-07-16__NHIS-user-centered-quality-report.json"

PREPROCESSING_VERSION = "2026-07-16.user-centered-v1"
CLAIM_SHA256 = "f346a5609972edc994a1379a0745950a7e4120d62648490594d734ceb916c1d4"
STATS_SHA256 = "c3499e23b515c5e8ca7a449927977ec5dd05cdd2d1050b6b3e5364910c68ddf9"
FORM_SHA256 = "3ab6006ad6a25b5d294dc65f323b669e285b7987d3061755b06fec079d4cab6b"

CLAIM_SOURCE_URL = "https://www.data.go.kr/data/15132486/fileData.do"
STATS_SOURCE_URL = "https://www.data.go.kr/data/15144521/fileData.do"
FORM_SOURCE_URL = (
    "https://law.go.kr/LSW/flDownload.do?bylClsCd=200203&"
    "flNm=%5B%EB%B3%84%EC%A7%80+6%5D+%EC%9D%BC%EB%B0%98%EA%B1%B4%EA%B0%95"
    "%EA%B2%80%EC%A7%84+%EA%B2%B0%EA%B3%BC%ED%86%B5%EB%B3%B4%EC%84%9C&"
    "flSeq=160922671"
)
LAW_SOURCE_URL = "https://law.go.kr/LSW/admRulLsInfoP.do?admRulId=38208&efYd=0"
KDCA_SOURCE_URL = (
    "https://health.kdca.go.kr/healthinfo/biz/health/ntcnInfo/healthSourc/"
    "thtimtCntnts/thtimtCntntsView.do?thtimt_cntnts_sn=7"
)


CLAIM_HEADERS = [
    "검진청구항목기준년도",
    "건강검진청구항목코드",
    "건강검진청구항목코드명",
    "건강검진유형구분코드",
    "건강검진유형상세코드",
]

STATS_DIMENSIONS = ["검진사업년도", "직역", "연령(5세단위)", "성별"]


def metric(
    source_column: str,
    code: str,
    group: str,
    label: str,
    *,
    denominator: str | None = "SCREENED_COUNT",
    scope: str = "NONEXCLUSIVE_PERSON_COUNT",
    explanation: str,
) -> dict[str, Any]:
    return {
        "source_column": source_column,
        "metric_code": code,
        "metric_group": group,
        "user_label": label,
        "count_scope": scope,
        "denominator_metric_code": denominator,
        "blank_policy": "PRESERVE_NULL_NOT_ZERO",
        "relationship_between_metrics": "DO_NOT_SUM_ACROSS_METRICS",
        "can_sum_across_disjoint_cohorts": True,
        "app_surface": "BENCHMARK",
        "user_explanation": explanation,
        "caution": (
            "공개 집계 참고값이며 개인의 검사결과·진단·위험도를 뜻하지 않습니다. "
            "같은 사람이 여러 판정 또는 관리 항목에 중복 집계될 수 있습니다."
        ),
    }


METRICS = [
    metric(
        "대상인원",
        "ELIGIBLE_COUNT",
        "ELIGIBILITY",
        "검진 대상 인원",
        denominator=None,
        scope="COHORT_PERSON_COUNT",
        explanation="해당 연도·직역·연령대·성별에서 일반건강검진 대상자로 집계된 인원입니다.",
    ),
    metric(
        "수검인원",
        "SCREENED_COUNT",
        "PARTICIPATION",
        "검진 수검 인원",
        denominator="ELIGIBLE_COUNT",
        scope="COHORT_PERSON_COUNT",
        explanation="검진 대상자 중 실제로 건강검진을 받은 인원입니다.",
    ),
    metric("정상A", "NORMAL_A_COUNT", "OVERALL_STATUS", "정상A", explanation="검진 종합소견에서 정상A로 집계된 인원입니다."),
    metric("정상B_실인원", "NORMAL_B_PEOPLE_COUNT", "OVERALL_STATUS", "정상B(경계)", explanation="자가관리·예방조치가 필요한 정상B로 집계된 실인원입니다."),
    metric("정상B_비만관리", "NORMAL_B_OBESITY_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 비만 관리", explanation="정상B 중 비만 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_혈압관리", "NORMAL_B_BP_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 혈압 관리", explanation="정상B 중 혈압 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_이상지질혈증관리", "NORMAL_B_DYSLIPIDEMIA_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 이상지질혈증 관리", explanation="정상B 중 이상지질혈증 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_간기능관리", "NORMAL_B_LIVER_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 간기능 관리", explanation="정상B 중 간기능 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_당뇨관리", "NORMAL_B_GLUCOSE_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 혈당 관리", explanation="정상B 중 혈당 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_신장기능관리", "NORMAL_B_KIDNEY_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 신장기능 관리", explanation="정상B 중 신장기능 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_빈혈관리", "NORMAL_B_ANEMIA_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 빈혈 관리", explanation="정상B 중 빈혈 관리가 필요한 것으로 집계된 인원입니다."),
    metric("정상B_골다공증관리", "NORMAL_B_OSTEOPOROSIS_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 골다공증 관리", explanation="정상B 중 골다공증 관리가 필요한 것으로 집계된 인원입니다. 공란은 0이 아니라 데이터 없음입니다."),
    metric("정상B_기타질환관리", "NORMAL_B_OTHER_MANAGEMENT_COUNT", "NORMAL_B_MANAGEMENT", "정상B - 기타질환 관리", explanation="정상B 중 기타질환 관리가 필요한 것으로 집계된 인원입니다."),
    metric("일반질환의심_실인원", "GENERAL_DISEASE_SUSPECTED_PEOPLE_COUNT", "OVERALL_STATUS", "일반 질환의심", explanation="추적검사 또는 의료기관 진료가 필요한 일반 질환의심 실인원입니다."),
    metric("일반질환의심_폐결핵의심", "TB_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "폐결핵 의심", explanation="폐결핵 의심으로 집계된 인원입니다."),
    metric("일반질환의심_기타흉부질환의심", "OTHER_CHEST_DISEASE_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "기타 흉부질환 의심", explanation="기타 흉부질환 의심으로 집계된 인원입니다."),
    metric("일반질환의심_이상지질혈증의심", "DYSLIPIDEMIA_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "이상지질혈증 의심", explanation="이상지질혈증 의심으로 집계된 인원입니다."),
    metric("일반질환의심_간장질환의심", "LIVER_DISEASE_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "간장질환 의심", explanation="간장질환 의심으로 집계된 인원입니다."),
    metric("일반질환의심_신장질환의심", "KIDNEY_DISEASE_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "신장질환 의심", explanation="신장질환 의심으로 집계된 인원입니다."),
    metric("일반질환의심_빈혈증의심", "ANEMIA_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "빈혈 의심", explanation="빈혈 의심으로 집계된 인원입니다."),
    metric("일반질환의심_골다공증의심", "OSTEOPOROSIS_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "골다공증 의심", explanation="골다공증 의심으로 집계된 인원입니다. 공란은 0이 아니라 데이터 없음입니다."),
    metric("일반질환의심_기타질환의심", "OTHER_DISEASE_SUSPECTED_COUNT", "GENERAL_DISEASE_SUSPECTED", "기타질환 의심", explanation="기타질환 의심으로 집계된 인원입니다."),
    metric("고혈압당뇨병질환의심_실인원", "CARDIOMETABOLIC_SUSPECTED_PEOPLE_COUNT", "OVERALL_STATUS", "고혈압·당뇨병 질환의심", explanation="고혈압 또는 당뇨병 질환의심 실인원입니다."),
    metric("고혈압당뇨병질환의심_고혈압질환의심", "HYPERTENSION_SUSPECTED_COUNT", "CARDIOMETABOLIC_SUSPECTED", "고혈압 질환의심", explanation="고혈압 질환의심으로 집계된 인원입니다."),
    metric("고혈압당뇨병질환의심_당뇨질환의심", "DIABETES_SUSPECTED_COUNT", "CARDIOMETABOLIC_SUSPECTED", "당뇨병 질환의심", explanation="당뇨병 질환의심으로 집계된 인원입니다."),
    metric("유질환자_실인원", "KNOWN_CONDITION_PEOPLE_COUNT", "OVERALL_STATUS", "유질환자", explanation="검진 전 진단 및 치료 이력이 있는 유질환자 실인원입니다."),
    metric("유질환자_고혈압", "KNOWN_HYPERTENSION_COUNT", "KNOWN_CONDITION", "유질환자 - 고혈압", explanation="고혈압 유질환자로 집계된 인원입니다."),
    metric("유질환자_당뇨", "KNOWN_DIABETES_COUNT", "KNOWN_CONDITION", "유질환자 - 당뇨병", explanation="당뇨병 유질환자로 집계된 인원입니다."),
    metric("유질환자_이상지질혈증", "KNOWN_DYSLIPIDEMIA_COUNT", "KNOWN_CONDITION", "유질환자 - 이상지질혈증", explanation="이상지질혈증 유질환자로 집계된 인원입니다."),
    metric("유질환자_폐결핵", "KNOWN_TB_COUNT", "KNOWN_CONDITION", "유질환자 - 폐결핵", explanation="폐결핵 유질환자로 집계된 인원입니다."),
]

METRIC_BY_SOURCE = {row["source_column"]: row for row in METRICS}
METRIC_BY_CODE = {row["metric_code"]: row for row in METRICS}

EMPLOYMENT = {
    "공교": ("PUBLIC_EDUCATION", "공무원·교직원"),
    "지역": ("REGIONAL_INSURED", "지역가입자"),
    "직장": ("EMPLOYEE_INSURED", "직장가입자"),
}
SEX = {"남자": ("MALE", "남성"), "여자": ("FEMALE", "여성")}
AGE_BANDS = {
    "19세이하": ("LE_19", None, 19),
    "20~24세": ("AGE_20_24", 20, 24),
    "25~29세": ("AGE_25_29", 25, 29),
    "30~34세": ("AGE_30_34", 30, 34),
    "35~39세": ("AGE_35_39", 35, 39),
    "40~44세": ("AGE_40_44", 40, 44),
    "45~49세": ("AGE_45_49", 45, 49),
    "50~54세": ("AGE_50_54", 50, 54),
    "55~59세": ("AGE_55_59", 55, 59),
    "60~64세": ("AGE_60_64", 60, 64),
    "65~69세": ("AGE_65_69", 65, 69),
    "70~74세": ("AGE_70_74", 70, 74),
    "75~79세": ("AGE_75_79", 75, 79),
    "80~84세": ("AGE_80_84", 80, 84),
    "85세이상": ("GE_85", 85, None),
}


def form_field(
    page: int,
    section: str,
    source_label: str,
    field_code: str,
    user_label: str,
    value_type: str,
    unit: str | None,
    sensitivity: str,
    ingest_policy: str,
    *,
    app_surface: str = "MY_RESULTS",
    confirmation: bool = True,
    note: str = "",
    extraction: str = "PDF_TEXT_AND_VISUAL_REVIEW",
) -> dict[str, Any]:
    return {
        "source_page": page,
        "source_section": section,
        "source_label": source_label,
        "field_code": field_code,
        "user_display_label": user_label,
        "value_type": value_type,
        "canonical_unit": unit,
        "sensitivity_class": sensitivity,
        "app_surface": app_surface,
        "ingest_policy": ingest_policy,
        "user_confirmation_required": confirmation,
        "diagnostic_use_allowed": False,
        "extraction_method": extraction,
        "notes": note,
    }


RESULT_FORM_FIELDS = [
    form_field(1, "수검자 정보", "수검자 성명", "SUBJECT_NAME", "이름", "TEXT", None, "DIRECT_IDENTIFIER", "IDENTITY_VAULT_ONLY", confirmation=False),
    form_field(1, "수검자 정보", "주민등록번호", "NATIONAL_ID", "주민등록번호", "TEXT", None, "HIGH_RISK_IDENTIFIER", "DO_NOT_STORE_RAW", confirmation=False, note="앱 분석·로그·VDB에 저장하지 않고 별도 본인확인 체계로 분리합니다."),
    form_field(1, "수검자 정보", "검진일", "SCREENED_ON", "검진일", "DATE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", confirmation=False),
    form_field(1, "수검자 정보", "검진장소", "SCREENING_LOCATION", "검진기관/장소", "TEXT", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(1, "수검자 정보", "내원/출장", "SCREENING_VISIT_TYPE", "검진 방식", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(1, "건강검진 종합소견", "판정", "OVERALL_RESULT_FLAGS", "종합소견", "CODE_LIST", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", note="정상A·정상B·질환의심·유질환자는 중복 표시될 수 있어 단일 등급으로 평탄화하지 않습니다."),
    form_field(1, "관리 필요사항", "의심 질환", "FOLLOW_UP_CONDITION_FLAGS", "추적 진료가 필요한 항목", "CODE_LIST", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="FOLLOW_UP"),
    form_field(1, "관리 필요사항", "다음연도 3월 31일까지", "FOLLOW_UP_DUE_ON", "확진검사 기한", "DATE", None, "PERSONAL_HEALTH", "DERIVE_FROM_RULE_VERSION", app_surface="FOLLOW_UP", note="검진일과 적용 규정 버전을 함께 저장해 계산합니다."),
    form_field(1, "관리 필요사항", "유질환", "KNOWN_CONDITION_NOTES", "현재 치료 중인 질환", "TEXT", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="FOLLOW_UP"),
    form_field(1, "관리 필요사항", "생활습관 관리", "LIFESTYLE_MANAGEMENT_NOTES", "생활습관 관리 안내", "TEXT", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(1, "관리 필요사항", "기타", "SCREENING_FREE_TEXT_NOTES", "기타 안내", "TEXT", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", note="OCR 신뢰도가 낮거나 자유서술이면 반드시 사용자 확인을 받습니다."),
    form_field(2, "계측검사", "키", "HEIGHT", "키", "NUMERIC", "cm", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "몸무게", "WEIGHT", "몸무게", "NUMERIC", "kg", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "체질량지수", "BMI", "체질량지수", "NUMERIC", "kg/m2", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "허리둘레", "WAIST_CIRCUMFERENCE", "허리둘레", "NUMERIC", "cm", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "시력(좌/우)", "VISION_LEFT_RIGHT", "시력(좌/우)", "NUMERIC_PAIR", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "청력(좌/우)", "HEARING_LEFT_RIGHT", "청력(좌/우)", "NUMERIC_PAIR", "dB", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "수축기 혈압", "SYSTOLIC_BP", "수축기 혈압", "NUMERIC", "mmHg", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "계측검사", "이완기 혈압", "DIASTOLIC_BP", "이완기 혈압", "NUMERIC", "mmHg", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "혈색소", "HEMOGLOBIN", "혈색소", "NUMERIC", "g/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "공복혈당", "FASTING_GLUCOSE", "공복혈당", "NUMERIC", "mg/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "총콜레스테롤", "TOTAL_CHOLESTEROL", "총콜레스테롤", "NUMERIC", "mg/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "고밀도 콜레스테롤", "HDL_CHOLESTEROL", "HDL 콜레스테롤", "NUMERIC", "mg/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "중성지방", "TRIGLYCERIDES", "중성지방", "NUMERIC", "mg/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "저밀도 콜레스테롤", "LDL_CHOLESTEROL", "LDL 콜레스테롤", "NUMERIC", "mg/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "혈청 크레아티닌", "SERUM_CREATININE", "혈청 크레아티닌", "NUMERIC", "mg/dL", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "신사구체여과율", "EGFR", "신사구체여과율(e-GFR)", "NUMERIC", "mL/min/1.73m2", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "AST", "AST", "AST", "NUMERIC", "U/L", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "ALT", "ALT", "ALT", "NUMERIC", "U/L", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "혈액검사", "감마지티피", "GAMMA_GTP", "감마지티피(γ-GTP)", "NUMERIC", "U/L", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "요검사", "요단백", "URINE_PROTEIN", "요단백", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "영상검사", "흉부촬영", "CHEST_XRAY_RESULT", "흉부촬영 결과", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", note="폐결핵 진단검사이며 폐암 선별검사가 아닙니다."),
    form_field(2, "진찰(문진)", "과거병력", "PAST_MEDICAL_HISTORY", "과거병력", "TEXT", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "진찰(문진)", "약물치료", "CURRENT_MEDICATION", "현재 약물치료", "TEXT", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "성·연령별 검사", "B형간염", "HEPATITIS_B_RESULT", "B형간염 검사", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "성·연령별 검사", "C형간염", "HEPATITIS_C_RESULT", "C형간염 검사", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "정신건강검사", "우울증", "PHQ9_TOTAL", "우울증 선별검사(PHQ-9)", "INTEGER", "score", "PERSONAL_HEALTH", "STORE_ENCRYPTED", note="선별검사 결과이며 진단으로 표시하지 않습니다."),
    form_field(2, "정신건강검사", "조기정신증", "EARLY_PSYCHOSIS_RESULT", "조기정신증 선별검사", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", note="선별검사 결과이며 진단으로 표시하지 않습니다."),
    form_field(2, "골밀도검사", "골밀도", "BONE_DENSITY_RESULT", "골밀도 검사", "NUMERIC_OR_CODE", "T-score or mg/cm3", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "폐기능검사", "FEV1", "FEV1", "1초노력호기량(FEV1)", "NUMERIC", "L", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "폐기능검사", "FVC", "FVC", "노력성폐활량(FVC)", "NUMERIC", "L", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "폐기능검사", "FEV1/FVC", "FEV1_FVC_PERCENT", "FEV1/FVC", "NUMERIC", "%", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "폐기능검사", "FEV6", "FEV6", "6초노력호기량(FEV6)", "NUMERIC", "L", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "폐기능검사", "FEV1/FEV6", "FEV1_FEV6_PERCENT", "FEV1/FEV6", "NUMERIC", "%", "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(2, "인지기능검사", "인지기능장애", "KDSQC_TOTAL", "인지기능 선별검사", "INTEGER", "score", "PERSONAL_HEALTH", "STORE_ENCRYPTED", note="선별검사 결과이며 진단으로 표시하지 않습니다."),
    form_field(2, "노인기능평가", "노인기능평가", "OLDER_ADULT_FUNCTION_RESULT", "노인기능평가", "CODE_LIST", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED"),
    form_field(3, "심뇌혈관질환 위험평가", "평균 대비 발생 위험", "CVD_RISK_RATIO", "평균 대비 심뇌혈관질환 위험", "NUMERIC", "times", "PERSONAL_HEALTH", "STORE_SOURCE_REPORTED_ONLY", extraction="VISUAL_REVIEW_IMAGE_PAGE", note="검진기관이 산출한 값을 가져오며 검증된 위험모형 없이 앱에서 재계산하지 않습니다."),
    form_field(3, "심뇌혈관질환 위험평가", "향후 10년 발생 확률", "CVD_10Y_RISK", "향후 10년 심뇌혈관질환 발생 확률", "NUMERIC", "%", "PERSONAL_HEALTH", "STORE_SOURCE_REPORTED_ONLY", extraction="VISUAL_REVIEW_IMAGE_PAGE", note="검진기관이 산출한 값을 가져오며 확정 진단으로 해석하지 않습니다."),
    form_field(3, "심뇌혈관질환 위험평가", "심뇌혈관 나이", "CARDIOVASCULAR_AGE", "심뇌혈관 나이", "INTEGER", "years", "PERSONAL_HEALTH", "STORE_SOURCE_REPORTED_ONLY", extraction="VISUAL_REVIEW_IMAGE_PAGE"),
    form_field(4, "담배사용", "흡연 상태", "SMOKING_STATUS", "흡연 상태", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(4, "담배사용", "니코틴 의존도 평가", "NICOTINE_DEPENDENCE", "니코틴 의존도", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(4, "음주", "음주 위험", "ALCOHOL_RISK", "음주 위험", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(4, "운동", "신체활동", "PHYSICAL_ACTIVITY_ASSESSMENT", "신체활동 평가", "CODE_LIST", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(4, "영양", "영양 평가", "NUTRITION_ASSESSMENT", "영양 평가", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(4, "비만", "비만 평가", "OBESITY_LIFESTYLE_ASSESSMENT", "체중 관리 평가", "CODE", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN"),
    form_field(4, "생활습관 처방", "상담·교육·약물·연계", "LIFESTYLE_PRESCRIPTION", "생활습관 처방", "CODE_LIST", None, "PERSONAL_HEALTH", "STORE_ENCRYPTED", app_surface="CARE_PLAN", note="의료기관이 발행한 처방·연계 내용을 보존하며 앱이 새 치료를 제안한 것으로 표현하지 않습니다."),
]


DATA_ROLES = [
    {
        "source_id": "MOHW_RESULT_NOTICE_2026_6",
        "source_name": "일반건강검진 결과통보서",
        "authority": "보건복지부/국가법령정보센터",
        "data_role": "PERSONAL_HEALTH_RECORD_SCHEMA",
        "grain": "개인·검진일·검사항목",
        "app_surfaces": "MY_RESULTS|FOLLOW_UP|CARE_PLAN",
        "user_visible": True,
        "allowed_use": "사용자의 실제 검진 결과, 원문 판정, 추적 진료 일정과 생활습관 처방 표시",
        "prohibited_use": "OCR 미확인 값을 확정값으로 표시; 주민등록번호 원문을 분석·로그·VDB에 저장",
        "contains_personal_data": True,
        "vdb_policy": "NEVER_EMBED_PERSONAL_VALUES",
        "source_url": FORM_SOURCE_URL,
        "version_note": "별지 제6호서식, 개정 2026-01-01; 현행 고시 2026-01-07 시행",
    },
    {
        "source_id": "NHIS_COHORT_STATS_2023_12_31",
        "source_name": "직역별·성별·연령별 건강검진정보",
        "authority": "국민건강보험공단",
        "data_role": "PUBLIC_AGGREGATE_BENCHMARK",
        "grain": "연도·직역·5세 연령대·성별",
        "app_surfaces": "BENCHMARK",
        "user_visible": True,
        "allowed_use": "동일 집단의 수검률·판정 인원 비율을 참고용으로 표시",
        "prohibited_use": "개인 진단·위험 예측; 중복 판정 인원을 합산해 100% 분포로 표시; 공란을 0으로 대체",
        "contains_personal_data": False,
        "vdb_policy": "STRUCTURED_LOOKUP_NOT_EMBEDDING",
        "source_url": STATS_SOURCE_URL,
        "version_note": "2022~2023년 공개 집계; 빈칸은 데이터 없음",
    },
    {
        "source_id": "NHIS_CLAIM_CODES_2024_07_31",
        "source_name": "건강검진청구항목코드",
        "authority": "국민건강보험공단",
        "data_role": "INTERNAL_BILLING_REFERENCE",
        "grain": "적용연도·청구항목코드",
        "app_surfaces": "INTERNAL_ETL_ONLY",
        "user_visible": False,
        "allowed_use": "청구·수집 파이프라인의 내부 코드 매핑 및 역사 버전 추적",
        "prohibited_use": "청구항목 코드를 개인 검사결과 항목이나 판정 기준으로 표시",
        "contains_personal_data": False,
        "vdb_policy": "RELATIONAL_DICTIONARY_NOT_EMBEDDING",
        "source_url": CLAIM_SOURCE_URL,
        "version_note": "2001~2024년 이력; 첨부 CSV의 유형코드 헤더/값 불일치 품질 플래그 필요",
    },
    {
        "source_id": "MOHW_SCREENING_RULE_2026_6",
        "source_name": "건강검진 실시기준",
        "authority": "보건복지부/국가법령정보센터",
        "data_role": "VERSIONED_CLASSIFICATION_RULE",
        "grain": "규칙 버전·검사항목·성별/연령 조건",
        "app_surfaces": "RESULT_CLASSIFICATION",
        "user_visible": True,
        "allowed_use": "검진일에 유효한 국가건강검진 판정과 출처 표시",
        "prohibited_use": "질병 확정 진단·치료 결정; 과거 결과를 최신 규칙으로 덮어쓰기",
        "contains_personal_data": False,
        "vdb_policy": "RELATIONAL_RULE_ENGINE_NOT_EMBEDDING",
        "source_url": LAW_SOURCE_URL,
        "version_note": "보건복지부고시 제2026-6호, 2026-01-07 시행",
    },
    {
        "source_id": "KDCA_HEALTH_SCREENING_GUIDE_2021_11",
        "source_name": "알아두면 도움이 되는 건강검진",
        "authority": "질병관리청 국가건강정보포털",
        "data_role": "USER_EDUCATION_CONTENT",
        "grain": "건강정보 콘텐츠 문서",
        "app_surfaces": "EXPLANATION",
        "user_visible": True,
        "allowed_use": "검진 목적, 항목과 판정 용어를 쉬운 말로 설명",
        "prohibited_use": "2026년 판정 규칙의 우선 근거로 사용; 원문 전체를 허가 없이 VDB에 복제",
        "contains_personal_data": False,
        "vdb_policy": "LINK_OR_LICENSE_APPROVED_SUMMARY_ONLY",
        "source_url": KDCA_SOURCE_URL,
        "version_note": "게시 2021-11; 현행 규칙은 법령 원문으로 별도 검증",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path, expected_headers: list[str]) -> list[dict[str, str]]:
    with path.open(encoding="cp949", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_headers:
            raise ValueError(
                f"unexpected headers in {path.name}: {reader.fieldnames!r}"
            )
        return list(reader)


def parse_count(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    parsed = int(normalized)
    if parsed < 0:
        raise ValueError(f"negative count: {value!r}")
    return parsed


def ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 8)


def cohort_dimensions(row: dict[str, str]) -> dict[str, Any]:
    employment_code, employment_label = EMPLOYMENT[row["직역"].strip()]
    sex_code, sex_label = SEX[row["성별"].strip()]
    age_label = row["연령(5세단위)"].strip()
    age_code, age_lower, age_upper = AGE_BANDS[age_label]
    year = int(row["검진사업년도"].strip())
    return {
        "cohort_key": f"{year}:{employment_code}:{age_code}:{sex_code}",
        "screening_year": year,
        "employment_category_code": employment_code,
        "employment_category_label": employment_label,
        "age_band_code": age_code,
        "age_band_label": age_label,
        "age_lower_inclusive": age_lower,
        "age_upper_inclusive": age_upper,
        "sex_code": sex_code,
        "sex_label": sex_label,
    }


def normalize_claim_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_code[row["건강검진청구항목코드"].strip()].append(row)
    latest_year = max(int(row["검진청구항목기준년도"].strip()) for row in rows)
    active_codes = {
        row["건강검진청구항목코드"].strip()
        for row in rows
        if int(row["검진청구항목기준년도"].strip()) == latest_year
    }
    normalized: list[dict[str, Any]] = []
    for row in rows:
        year = int(row["검진청구항목기준년도"].strip())
        code = row["건강검진청구항목코드"].strip()
        name = row["건강검진청구항목코드명"].strip()
        raw_type_field = row["건강검진유형구분코드"].strip()
        raw_detail_field = row["건강검진유형상세코드"].strip()
        years = sorted(
            int(item["검진청구항목기준년도"].strip()) for item in by_code[code]
        )
        flags = [
            "SOURCE_TYPE_FIELD_CONTAINS_LABEL_NOT_CODE",
            "SOURCE_DETAIL_FIELD_CONTAINS_TYPE_CODE",
            "OFFICIAL_DETAIL_CODE_UNAVAILABLE_IN_ATTACHMENT",
        ]
        flags.append(
            "SOURCE_TYPE_FIELD_DUPLICATES_ITEM_NAME"
            if raw_type_field == name
            else "SOURCE_TYPE_FIELD_CONFLICTS_WITH_ITEM_NAME"
        )
        normalized.append(
            {
                "claim_basis_year": year,
                "claim_item_code": code,
                "claim_item_name": name,
                "source_type_field_raw": raw_type_field,
                "source_detail_field_raw": raw_detail_field,
                "type_code_normalized": raw_detail_field,
                "code_family_prefix": code[:3],
                "official_detail_code": None,
                "first_seen_year": years[0],
                "last_seen_year": years[-1],
                "is_latest_year_row": year == latest_year,
                "is_active_in_latest_year": code in active_codes,
                "user_visibility": "INTERNAL_ONLY",
                "app_usage": "CLAIM_ETL_MAPPING_ONLY",
                "quality_flags": "|".join(flags),
            }
        )
    return normalized


def normalize_stats_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cohort_rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    for source in rows:
        dims = cohort_dimensions(source)
        counts = {
            definition["metric_code"]: parse_count(source[definition["source_column"]])
            for definition in METRICS
        }
        target = counts["ELIGIBLE_COUNT"]
        screened = counts["SCREENED_COUNT"]
        status_codes = [
            "NORMAL_A_COUNT",
            "NORMAL_B_PEOPLE_COUNT",
            "GENERAL_DISEASE_SUSPECTED_PEOPLE_COUNT",
            "CARDIOMETABOLIC_SUSPECTED_PEOPLE_COUNT",
            "KNOWN_CONDITION_PEOPLE_COUNT",
        ]
        missing_count = sum(value is None for value in counts.values())
        status_total = sum(counts[code] or 0 for code in status_codes)
        flags = ["STATUS_COUNTS_NONEXCLUSIVE"]
        if missing_count:
            flags.append("SOURCE_HAS_NULL_NOT_ZERO")
        cohort_rows.append(
            {
                **dims,
                "eligible_count": target,
                "screened_count": screened,
                "screening_participation_rate": ratio(screened, target),
                "normal_a_count": counts["NORMAL_A_COUNT"],
                "normal_a_rate": ratio(counts["NORMAL_A_COUNT"], screened),
                "normal_b_people_count": counts["NORMAL_B_PEOPLE_COUNT"],
                "normal_b_rate": ratio(counts["NORMAL_B_PEOPLE_COUNT"], screened),
                "general_disease_suspected_people_count": counts[
                    "GENERAL_DISEASE_SUSPECTED_PEOPLE_COUNT"
                ],
                "general_disease_suspected_rate": ratio(
                    counts["GENERAL_DISEASE_SUSPECTED_PEOPLE_COUNT"], screened
                ),
                "cardiometabolic_suspected_people_count": counts[
                    "CARDIOMETABOLIC_SUSPECTED_PEOPLE_COUNT"
                ],
                "cardiometabolic_suspected_rate": ratio(
                    counts["CARDIOMETABOLIC_SUSPECTED_PEOPLE_COUNT"], screened
                ),
                "known_condition_people_count": counts[
                    "KNOWN_CONDITION_PEOPLE_COUNT"
                ],
                "known_condition_rate": ratio(
                    counts["KNOWN_CONDITION_PEOPLE_COUNT"], screened
                ),
                "status_count_sum_for_quality_check": status_total,
                "status_counts_are_nonexclusive": True,
                "source_null_metric_count": missing_count,
                "quality_flags": "|".join(flags),
            }
        )
        for definition in METRICS:
            count = counts[definition["metric_code"]]
            denominator_code = definition["denominator_metric_code"]
            denominator = counts.get(denominator_code) if denominator_code else None
            long_rows.append(
                {
                    **dims,
                    "metric_code": definition["metric_code"],
                    "metric_group": definition["metric_group"],
                    "metric_label": definition["user_label"],
                    "count": count,
                    "value_status": "REPORTED" if count is not None else "NOT_AVAILABLE",
                    "denominator_metric_code": denominator_code,
                    "denominator_count": denominator,
                    "rate": ratio(count, denominator),
                    "rate_semantics": (
                        "PARTICIPATION_RATE"
                        if definition["metric_code"] == "SCREENED_COUNT"
                        else "NONEXCLUSIVE_RATE_AMONG_SCREENED"
                        if denominator_code == "SCREENED_COUNT"
                        else "NOT_APPLICABLE"
                    ),
                    "app_surface": "BENCHMARK",
                    "individual_inference_allowed": False,
                    "quality_flags": (
                        "SOURCE_NULL_PRESERVED"
                        if count is None
                        else "NONEXCLUSIVE_METRIC_DO_NOT_SUM"
                    ),
                }
            )
    return cohort_rows, long_rows


def verify_pdf(path: Path) -> dict[str, Any]:
    anchors = {
        1: ["일반건강검진 결과통보서", "건강검진 종합소견", "주민등록번호"],
        2: ["체질량지수", "공복혈당", "신사구체여과율"],
        4: ["생활습관평가 결과지", "니코틴 의존도", "운동 처방전"],
    }
    with pdfplumber.open(path) as document:
        pages = [(page.extract_text() or "") for page in document.pages]
    checks = []
    for page_number, terms in anchors.items():
        text = "".join(pages[page_number - 1].split())
        missing = [term for term in terms if "".join(term.split()) not in text]
        checks.append(
            {
                "page": page_number,
                "terms": terms,
                "missing": missing,
                "passed": not missing,
            }
        )
    return {
        "page_count": len(pages),
        "anchor_checks": checks,
        "page_3_extraction": "IMAGE_PAGE_VISUALLY_REVIEWED",
    }


def csv_text(rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        rendered = {
            key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, (dict, list))
            else value
            for key, value in row.items()
        }
        writer.writerow(rendered)
    return buffer.getvalue()


def artifact_texts(
    claim_rows: list[dict[str, str]],
    stats_rows: list[dict[str, str]],
    pdf_info: dict[str, Any],
) -> dict[str, str]:
    claim_history = normalize_claim_rows(claim_rows)
    claim_current = [row for row in claim_history if row["is_latest_year_row"]]
    cohort_summary, metrics_long = normalize_stats_rows(stats_rows)

    claim_fieldnames = list(claim_history[0])
    cohort_fieldnames = list(cohort_summary[0])
    long_fieldnames = list(metrics_long[0])
    metric_fieldnames = list(METRICS[0])
    form_fieldnames = list(RESULT_FORM_FIELDS[0])
    role_fieldnames = list(DATA_ROLES[0])

    source_blank_cells = sum(
        1
        for row in stats_rows
        for definition in METRICS
        if row[definition["source_column"]].strip() == ""
    )
    status_overlap_rows = sum(
        row["status_count_sum_for_quality_check"] > (row["screened_count"] or 0)
        for row in cohort_summary
    )
    field4_equals_name = sum(
        row["건강검진유형구분코드"].strip()
        == row["건강검진청구항목코드명"].strip()
        for row in claim_rows
    )
    claim_composite_keys = {
        (
            row["검진청구항목기준년도"].strip(),
            row["건강검진청구항목코드"].strip(),
        )
        for row in claim_rows
    }
    cohort_keys = {row["cohort_key"] for row in cohort_summary}
    all_reported_counts_within_screened = all(
        item["count"] is None
        or item["metric_code"] in {"ELIGIBLE_COUNT", "SCREENED_COUNT"}
        or item["count"] <= (item["denominator_count"] or 0)
        for item in metrics_long
    )

    checks = {
        "claim_source_checksum": True,
        "statistics_source_checksum": True,
        "result_form_source_checksum": True,
        "claim_expected_headers": list(claim_rows[0]) == CLAIM_HEADERS,
        "claim_composite_key_unique": len(claim_composite_keys) == len(claim_rows),
        "claim_latest_year_row_count_243": len(claim_current) == 243,
        "statistics_expected_180_cohorts": len(cohort_summary) == 180,
        "statistics_full_cartesian_grain": len(cohort_keys) == 2 * 3 * 15 * 2,
        "statistics_screened_not_above_eligible": all(
            row["screened_count"] <= row["eligible_count"] for row in cohort_summary
        ),
        "statistics_reported_counts_within_screened": all_reported_counts_within_screened,
        "statistics_blanks_preserved_as_null": any(
            row["value_status"] == "NOT_AVAILABLE" and row["count"] is None
            for row in metrics_long
        ),
        "statistics_status_overlap_detected": status_overlap_rows == len(cohort_summary),
        "result_form_page_count_4": pdf_info["page_count"] == 4,
        "result_form_text_anchors": all(
            check["passed"] for check in pdf_info["anchor_checks"]
        ),
        "result_form_field_codes_unique": len(
            {row["field_code"] for row in RESULT_FORM_FIELDS}
        )
        == len(RESULT_FORM_FIELDS),
    }
    quality = {
        "status": "PASS_WITH_WARNINGS" if all(checks.values()) else "FAIL",
        "preprocessing_version": PREPROCESSING_VERSION,
        "dataset": {
            "claim_history_rows": len(claim_history),
            "claim_current_rows": len(claim_current),
            "claim_distinct_codes": len(
                {row["claim_item_code"] for row in claim_history}
            ),
            "claim_years": sorted(
                {row["claim_basis_year"] for row in claim_history}
            ),
            "cohort_rows": len(cohort_summary),
            "metric_dictionary_rows": len(METRICS),
            "metric_long_rows": len(metrics_long),
            "result_form_field_rows": len(RESULT_FORM_FIELDS),
            "source_blank_cells": source_blank_cells,
            "status_overlap_rows": status_overlap_rows,
        },
        "checks": checks,
        "findings": [
            {
                "severity": "HIGH",
                "confidence": "HIGH",
                "finding": "집계 판정 인원은 상호배타적이지 않음",
                "evidence": f"{status_overlap_rows}/{len(cohort_summary)}개 코호트에서 주요 판정 실인원 합계가 수검인원을 초과",
                "risk": "판정 비율을 합산해 100% 구성비로 표시하면 사용자를 오도함",
                "remediation": "각 지표를 독립 참고율로 표시하고 stacked/pie 시각화를 금지",
            },
            {
                "severity": "HIGH",
                "confidence": "HIGH",
                "finding": "청구코드 CSV의 유형코드 헤더와 값이 어긋남",
                "evidence": f"유형구분코드 필드가 {field4_equals_name}/{len(claim_rows)}행에서 코드명이랑 동일하고, 마지막 필드는 전 행에서 코드 첫 글자와 동일",
                "risk": "헤더를 그대로 신뢰하면 유형코드와 상세코드를 잘못 적재함",
                "remediation": "원문 필드를 보존하고 마지막 필드만 추론된 유형코드로 별도 저장; 상세코드는 null로 유지",
            },
            {
                "severity": "MEDIUM",
                "confidence": "HIGH",
                "finding": "집계 CSV 공란은 0이 아님",
                "evidence": f"{source_blank_cells}개 수치 셀이 공란이며 공식 API 설명은 공란을 데이터 없음으로 정의",
                "risk": "0 대체 시 비해당·미집계 집단을 발생 없음으로 오해",
                "remediation": "null과 0을 구분하고 공란 비율은 계산하지 않음",
            },
            {
                "severity": "MEDIUM",
                "confidence": "HIGH",
                "finding": "청구항목코드는 연도별 이력 데이터",
                "evidence": f"{len(claim_rows)}행이지만 고유 코드는 {len({row['건강검진청구항목코드'].strip() for row in claim_rows})}개",
                "risk": "코드 단독 기본키 사용 시 과거 정의가 덮어써짐",
                "remediation": "적용연도+청구항목코드를 복합키로 사용",
            },
            {
                "severity": "HIGH",
                "confidence": "HIGH",
                "finding": "결과통보서에 직접식별정보와 민감건강정보가 함께 있음",
                "evidence": "1·4쪽에 성명과 주민등록번호, 전 페이지에 검진결과 및 생활습관 정보 포함",
                "risk": "분석 로그나 VDB에 원문을 적재하면 불필요한 개인정보 노출",
                "remediation": "주민등록번호 원문 미저장, 개인 결과 암호화, 개인 값을 VDB에 임베딩하지 않음",
            },
            {
                "severity": "MEDIUM",
                "confidence": "HIGH",
                "finding": "질병관리청 안내문은 2021년 설명 자료",
                "evidence": "게시 시점 2021-11; 현행 법령은 보건복지부고시 제2026-6호",
                "risk": "과거 설명 문구를 최신 판정 규칙으로 사용하면 기준 불일치 가능",
                "remediation": "사용자 설명에만 사용하고 규칙은 현행 법령/PDF 버전으로 적용",
            },
        ],
        "known_limitations": [
            "공개 집계는 개인별 검사수치가 없어 개인화 위험 예측이나 진단 모델 학습에 사용할 수 없음",
            "직역은 보험 자격 집계 범주이며 사용자의 직업·건강 상태를 설명하는 인과변수가 아님",
            "청구코드 첨부파일에서 공식 상세구분코드가 손실되어 코드 앞 3자리는 참고용 family prefix로만 제공",
            "결과통보서 3쪽은 이미지 기반이라 자동 텍스트 추출 대신 시각 검수된 필드 사양을 사용",
            "모든 판정은 국가건강검진 분류이며 질병 확정 진단 또는 치료 지시가 아님",
        ],
        "sources": [
            {
                "source_id": "NHIS_CLAIM_CODES_2024_07_31",
                "sha256": CLAIM_SHA256,
                "encoding": "CP949",
                "rows": len(claim_rows),
                "url": CLAIM_SOURCE_URL,
            },
            {
                "source_id": "NHIS_COHORT_STATS_2023_12_31",
                "sha256": STATS_SHA256,
                "encoding": "CP949",
                "rows": len(stats_rows),
                "url": STATS_SOURCE_URL,
            },
            {
                "source_id": "MOHW_RESULT_NOTICE_2026_6",
                "sha256": FORM_SHA256,
                "pages": pdf_info["page_count"],
                "url": FORM_SOURCE_URL,
            },
        ],
    }

    contract = {
        "contract_version": PREPROCESSING_VERSION,
        "principles": [
            "개인 결과, 공개 집계, 내부 청구코드, 판정 규칙, 설명 콘텐츠를 역할별로 분리한다.",
            "공개 집계는 비교 참고만 제공하고 개인의 진단·위험으로 변환하지 않는다.",
            "공란은 null로, 실제 0은 0으로 보존한다.",
            "판정·관리 항목은 중복 가능하므로 상호배타 분포로 표시하지 않는다.",
            "검진일에 유효한 규칙 버전을 적용하고 출처와 판정일을 함께 보존한다.",
            "주민등록번호 원문과 개인 검진값은 분석 로그·VDB에 넣지 않는다.",
        ],
        "app_surfaces": {
            "MY_RESULTS": "결과통보서에서 확인된 개인 수치와 원문 판정",
            "FOLLOW_UP": "의심 항목, 확진검사 안내, 사용자 확인 상태",
            "CARE_PLAN": "의료기관이 발행한 생활습관 평가·처방",
            "BENCHMARK": "같은 공개 코호트의 독립 참고율",
            "INTERNAL_ETL_ONLY": "청구 및 수집 코드 매핑",
            "EXPLANATION": "쉬운 용어 설명과 출처 링크",
        },
        "benchmark_contract": {
            "grain": ["screening_year", "employment_category", "age_band", "sex"],
            "primary_key": "cohort_key",
            "blank_semantics": "NOT_AVAILABLE",
            "zero_semantics": "REPORTED_ZERO",
            "rate_denominator": {
                "SCREENED_COUNT": "ELIGIBLE_COUNT",
                "outcome_and_management_metrics": "SCREENED_COUNT",
            },
            "nonexclusive": True,
            "forbidden_visuals": ["PIE_OF_STATUS_COUNTS", "STACKED_100_PERCENT_STATUS"],
        },
        "claim_code_contract": {
            "primary_key": ["claim_basis_year", "claim_item_code"],
            "user_visible": False,
            "result_item_mapping": "NOT_DIRECT",
            "header_mismatch_policy": "PRESERVE_RAW_AND_FLAG; DO_NOT_INVENT_DETAIL_CODE",
        },
        "personal_data_contract": {
            "resident_registration_number": "DO_NOT_STORE_RAW",
            "personal_values": "ENCRYPT_AND_KEEP_OUT_OF_VDB",
            "ocr_values": "REQUIRE_USER_CONFIRMATION_BEFORE_PERSONALIZED_USE",
            "risk_scores": "STORE_SOURCE_REPORTED_ONLY_UNLESS_MODEL_VALIDATED",
        },
        "source_roles": DATA_ROLES,
        "output_files": [
            CLAIM_HISTORY_CSV,
            CLAIM_CURRENT_CSV,
            COHORT_SUMMARY_CSV,
            METRICS_LONG_CSV,
            METRIC_DICTIONARY_CSV,
            RESULT_FORM_FIELDS_CSV,
            DATA_ROLE_CSV,
            QUALITY_JSON,
        ],
    }

    return {
        CLAIM_HISTORY_CSV: csv_text(claim_history, claim_fieldnames),
        CLAIM_CURRENT_CSV: csv_text(claim_current, claim_fieldnames),
        COHORT_SUMMARY_CSV: csv_text(cohort_summary, cohort_fieldnames),
        METRICS_LONG_CSV: csv_text(metrics_long, long_fieldnames),
        METRIC_DICTIONARY_CSV: csv_text(METRICS, metric_fieldnames),
        RESULT_FORM_FIELDS_CSV: csv_text(RESULT_FORM_FIELDS, form_fieldnames),
        DATA_ROLE_CSV: csv_text(DATA_ROLES, role_fieldnames),
        DATA_CONTRACT_JSON: json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        QUALITY_JSON: json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
    }


def choose_input(explicit: Path | None, raw: Path, download: Path) -> Path:
    if explicit is not None:
        return explicit
    return raw if raw.exists() else download


def copy_source(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)


def write_or_check(
    artifacts: dict[str, str], output_dir: Path, check: bool
) -> list[str]:
    errors: list[str] = []
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in artifacts.items():
        path = output_dir / filename
        if check:
            if not path.exists():
                errors.append(f"missing artifact: {path}")
            elif path.read_text(encoding="utf-8") != content:
                errors.append(f"out-of-date artifact: {path}")
        else:
            path.write_text(content, encoding="utf-8")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim-codes", type=Path)
    parser.add_argument("--statistics", type=Path)
    parser.add_argument("--result-form", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    claim_path = choose_input(args.claim_codes, RAW_CLAIM, DOWNLOAD_CLAIM)
    stats_path = choose_input(args.statistics, RAW_STATS, DOWNLOAD_STATS)
    form_path = choose_input(args.result_form, RAW_FORM, DOWNLOAD_FORM)
    inputs = [claim_path, stats_path, form_path]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        print(json.dumps({"status": "FAIL", "missing_inputs": missing}, ensure_ascii=False, indent=2))
        return 1

    checksum_errors = []
    for path, expected in (
        (claim_path, CLAIM_SHA256),
        (stats_path, STATS_SHA256),
        (form_path, FORM_SHA256),
    ):
        actual = sha256(path)
        if actual != expected:
            checksum_errors.append(
                f"checksum mismatch for {path}: expected {expected}, actual {actual}"
            )
    if checksum_errors:
        print(json.dumps({"status": "FAIL", "errors": checksum_errors}, ensure_ascii=False, indent=2))
        return 1

    if not args.check:
        copy_source(claim_path, RAW_CLAIM)
        copy_source(stats_path, RAW_STATS)
        copy_source(form_path, RAW_FORM)
        claim_path, stats_path, form_path = RAW_CLAIM, RAW_STATS, RAW_FORM

    claim_rows = read_csv(claim_path, CLAIM_HEADERS)
    stats_rows = read_csv(stats_path, STATS_DIMENSIONS + [row["source_column"] for row in METRICS])
    pdf_info = verify_pdf(form_path)
    artifacts = artifact_texts(claim_rows, stats_rows, pdf_info)
    sync_errors = write_or_check(artifacts, args.output_dir, args.check)
    quality = json.loads(artifacts[QUALITY_JSON])
    errors = sync_errors
    if quality["status"] == "FAIL":
        errors.append("one or more data quality checks failed")

    summary = {
        "status": "PASS" if not errors else "FAIL",
        "quality_status": quality["status"],
        "claim_history_rows": quality["dataset"]["claim_history_rows"],
        "claim_current_rows": quality["dataset"]["claim_current_rows"],
        "cohort_rows": quality["dataset"]["cohort_rows"],
        "metric_long_rows": quality["dataset"]["metric_long_rows"],
        "result_form_fields": quality["dataset"]["result_form_field_rows"],
        "output_dir": str(args.output_dir),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
