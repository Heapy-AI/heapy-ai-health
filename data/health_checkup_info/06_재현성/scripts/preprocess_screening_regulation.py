#!/usr/bin/env python3
"""Preprocess the 2026 Korean national health-screening regulation.

The source PDFs contain merged cells and multi-input decision rules. Blind table
extraction is not safe enough for a medical product, so this script combines:

1. checksum and page-anchor verification against the official PDFs;
2. a visually reviewed, versioned rule specification;
3. deterministic JSON/CSV generation and boundary-case validation.

The generated rules are screening classifications, not diagnostic criteria.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

try:
    import pdfplumber
except ImportError as exc:  # pragma: no cover - exercised by CLI users
    raise SystemExit(
        "pdfplumber is required. Install requirements-vdb.txt before running."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "storage/source_document/mohw_screening/raw"
OUTPUT_DIR = ROOT / "storage/source_document/mohw_screening/normalized"

DATASET_JSON = "2026-01-07__MOHW-2026-6__screening-regulation.json"
ITEMS_CSV = "2026-01-07__MOHW-2026-6__screening-items.csv"
RULES_CSV = "2026-01-07__MOHW-2026-6__screening-rules.csv"
ELIGIBILITY_CSV = "2026-01-07__MOHW-2026-6__screening-eligibility.csv"
QUALITY_JSON = "2026-01-07__MOHW-2026-6__quality-report.json"


DOCUMENTS = [
    {
        "document_code": "MOHW_SCREENING_2026_6_APPENDIX_1",
        "title": "건강검진 실시기준 [별표 1] 일반건강검진 검사항목, 검진비용, 대상자 및 검사방법",
        "path": RAW_DIR / "2026-01-07__MOHW-2026-6__appendix-1-items.pdf",
        "source_url": "https://law.go.kr/LSW/flDownload.do?flSeq=160922447",
        "law_attachment_id": "3146325",
        "sha256": "0c61bb0f3d5b63d83c3fa36b56100e90a8925fd4c5afc2baf836d848c83515d9",
        "page_count": 7,
        "page_anchors": {
            1: ["일반건강검진", "혈압측정", "흉부방사선"],
            2: ["요단백", "공복혈당", "저밀도"],
            3: ["B형간염", "C형간염", "골밀도", "폐기능"],
            4: ["인지기능장애", "생활습관평가"],
            5: ["PHQ-9", "CAPE-15", "노인신체기능검사"],
            6: ["구강검진", "치면세균막"],
            7: ["분류번호"],
        },
    },
    {
        "document_code": "MOHW_SCREENING_2026_6_APPENDIX_4",
        "title": "건강검진 실시기준 [별표 4] 일반건강검진 및 의료급여생애전환기검진 결과 판정기준",
        "path": RAW_DIR / "2026-01-07__MOHW-2026-6__appendix-4-judgement.pdf",
        "source_url": "https://law.go.kr/LSW/flDownload.do?flSeq=160922523",
        "law_attachment_id": "3146331",
        "sha256": "5b581fa2bb092f340411f507cd56195adf23737d51ec424c09ff9225d159a16b",
        "page_count": 4,
        "page_anchors": {
            1: ["정상A", "정상B", "일반 질환의심", "유질환자"],
            2: ["공복 혈당", "고밀도", "신사구체여과율"],
            3: ["PHQ-9", "CAPE-15", "KDSQ-C", "만성폐쇄성"],
            4: ["치아우식증", "치주질환", "치면세균막"],
        },
    },
    {
        "document_code": "MOHW_SCREENING_2026_6_APPENDIX_4_DETAIL",
        "title": "건강검진 실시기준 [별표 4의 별첨] 검사항목별 판정기준",
        "path": RAW_DIR / "2026-01-07__MOHW-2026-6__v2026-6.pdf",
        "source_url": "https://law.go.kr/LSW/flDownload.do?flSeq=160922929",
        "law_attachment_id": "3146451",
        "sha256": "5f804efa7257c067eabe8084cff6b9fb3d140f8f33e10234fc5423351f6ed11a",
        "page_count": 3,
        "page_anchors": {
            1: ["공복 혈당", "고밀도", "신사구체여과율"],
            2: ["PHQ-9", "CAPE-15", "KDSQ-C", "만성폐쇄성"],
            3: ["치아우식증", "치주질환", "치면세균막"],
        },
    },
]


RESULT_DEFINITIONS = [
    {
        "result_code": "NORMAL_A",
        "label_ko": "정상A",
        "severity_rank": 0,
        "definition": "검진 결과 건강이 양호한 경우",
    },
    {
        "result_code": "NORMAL_B",
        "label_ko": "정상B(경계)",
        "severity_rank": 1,
        "definition": "자가관리 및 예방조치가 필요한 경우",
    },
    {
        "result_code": "GENERAL_DISEASE_SUSPECTED",
        "label_ko": "일반 질환의심",
        "severity_rank": 2,
        "definition": "추적검사 또는 전문 의료기관의 진단과 진료가 필요한 경우",
    },
    {
        "result_code": "CARDIOMETABOLIC_DISEASE_SUSPECTED",
        "label_ko": "고혈압·당뇨병·이상지질혈증 질환의심",
        "severity_rank": 2,
        "definition": "고혈압, 당뇨병 또는 이상지질혈증이 의심되어 진료와 검사 등이 필요한 경우",
    },
    {
        "result_code": "KNOWN_DISEASE",
        "label_ko": "유질환자",
        "severity_rank": 2,
        "definition": "고혈압, 당뇨병, 이상지질혈증, 폐결핵, 우울증, 조기정신증, C형간염 또는 만성폐쇄성폐질환으로 진단받고 현재 약물 치료를 받는 경우",
    },
    {
        "result_code": "ORAL_GOOD",
        "label_ko": "구강 양호",
        "severity_rank": 0,
        "definition": "구강 관련 이상 소견과 치료가 필요한 우식치아가 없는 경우",
    },
    {
        "result_code": "ORAL_CAUTION",
        "label_ko": "구강 주의",
        "severity_rank": 1,
        "definition": "수복치아, 구강악습관, 보통 수준 치면세균막 또는 생활습관 위험이 있는 경우",
    },
    {
        "result_code": "ORAL_DISEASE_SUSPECTED",
        "label_ko": "구강 질환의심",
        "severity_rank": 2,
        "definition": "우식 의심치아, 경증 치은염·치석 또는 개선요망 치면세균막이 있는 경우",
    },
    {
        "result_code": "ORAL_TREATMENT_REQUIRED",
        "label_ko": "구강 치료필요",
        "severity_rank": 3,
        "definition": "명확한 우식치아 또는 중증 치석·치주낭 등으로 치료가 필요한 경우",
    },
]


def item(
    code: str,
    name: str,
    domain: str,
    value_type: str,
    unit: str | None = None,
    *,
    integer_only: bool = False,
    allowed_values: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "item_code": code,
        "display_name_ko": name,
        "domain": domain,
        "value_type": value_type,
        "canonical_unit": unit,
        "integer_only": integer_only,
        "allowed_values": allowed_values or [],
    }


ITEMS = [
    item("CHEST_XRAY_RESULT", "흉부방사선촬영 결과", "CHEST", "CODE", allowed_values=["NORMAL", "INACTIVE_TB", "OTHER_ABNORMAL", "IMAGE_POOR", "NOT_TAKEN"]),
    item("SUBJECT_SEX", "성별", "DEMOGRAPHIC", "CODE", allowed_values=["MALE", "FEMALE"]),
    item("SYSTOLIC_BP", "수축기 혈압", "CARDIOVASCULAR", "NUMERIC", "mmHg"),
    item("DIASTOLIC_BP", "이완기 혈압", "CARDIOVASCULAR", "NUMERIC", "mmHg"),
    item("BMI", "체질량지수", "BODY_COMPOSITION", "NUMERIC", "kg/m2"),
    item("WAIST_CIRCUMFERENCE", "허리둘레", "BODY_COMPOSITION", "NUMERIC", "cm"),
    item("HEMOGLOBIN", "혈색소", "HEMATOLOGY", "NUMERIC", "g/dL"),
    item("FASTING_GLUCOSE", "공복혈당", "GLUCOSE_METABOLISM", "NUMERIC", "mg/dL"),
    item("TOTAL_CHOLESTEROL", "총콜레스테롤", "LIPID", "NUMERIC", "mg/dL"),
    item("HDL_CHOLESTEROL", "고밀도(HDL) 콜레스테롤", "LIPID", "NUMERIC", "mg/dL"),
    item("TRIGLYCERIDES", "중성지방", "LIPID", "NUMERIC", "mg/dL"),
    item("LDL_CHOLESTEROL", "저밀도(LDL) 콜레스테롤", "LIPID", "NUMERIC", "mg/dL"),
    item("AST", "에이에스티(AST/SGOT)", "LIVER", "NUMERIC", "U/L"),
    item("ALT", "에이엘티(ALT/SGPT)", "LIVER", "NUMERIC", "U/L"),
    item("GAMMA_GTP", "감마지티피(γ-GTP)", "LIVER", "NUMERIC", "U/L"),
    item("URINE_PROTEIN", "요단백", "KIDNEY", "CODE", allowed_values=["NEGATIVE", "TRACE", "POSITIVE_1", "POSITIVE_2", "POSITIVE_3", "POSITIVE_4"]),
    item("SERUM_CREATININE", "혈청크레아티닌", "KIDNEY", "NUMERIC", "mg/dL"),
    item("EGFR", "신사구체여과율(e-GFR)", "KIDNEY", "NUMERIC", "mL/min/1.73m2"),
    item("BONE_DENSITY_T_SCORE", "골밀도 T-score", "BONE", "NUMERIC", "T-score"),
    item("PERIPHERAL_BONE_DENSITY", "말단골 정량적 골밀도", "BONE", "NUMERIC", "mg/cm3"),
    item("LOWER_LIMB_FUNCTION_SECONDS", "하지기능 검사시간", "PHYSICAL_FUNCTION", "NUMERIC", "s", integer_only=True),
    item("BALANCE_EYES_CLOSED_SECONDS", "평형성(눈감은 상태)", "PHYSICAL_FUNCTION", "NUMERIC", "s", integer_only=True),
    item("BALANCE_EYES_OPEN_SECONDS", "평형성(눈 뜬 상태)", "PHYSICAL_FUNCTION", "NUMERIC", "s", integer_only=True),
    item("PHQ9_TOTAL", "PHQ-9 총점", "MENTAL_HEALTH", "NUMERIC", "score", integer_only=True),
    item("PHQ9_ITEM9", "PHQ-9 9번 문항", "MENTAL_HEALTH", "NUMERIC", "score", integer_only=True),
    item("CAPE15_FREQUENCY_TOTAL", "CAPE-15 빈도 총점", "MENTAL_HEALTH", "NUMERIC", "score", integer_only=True),
    item("CAPE15_DISTRESS_TOTAL", "CAPE-15 고통 총점", "MENTAL_HEALTH", "NUMERIC", "score", integer_only=True),
    item("KDSQC_TOTAL", "KDSQ-C 총점", "COGNITIVE", "NUMERIC", "score", integer_only=True),
    item("WHISPER_LEFT_CORRECT", "귓속말 검사 왼쪽 정답수", "HEARING", "NUMERIC", "count", integer_only=True),
    item("WHISPER_RIGHT_CORRECT", "귓속말 검사 오른쪽 정답수", "HEARING", "NUMERIC", "count", integer_only=True),
    item("PURE_TONE_DB", "순음청력검사", "HEARING", "NUMERIC", "dB"),
    item("FEV1_FVC_PERCENT", "FEV1/FVC", "PULMONARY", "NUMERIC", "%"),
    item("FEV1_PERCENT", "FEV1 예측치 대비", "PULMONARY", "NUMERIC", "%"),
    item("FVC_PERCENT", "FVC 예측치 대비", "PULMONARY", "NUMERIC", "%"),
    item("FEV1_FEV6_PERCENT", "FEV1/FEV6", "PULMONARY", "NUMERIC", "%"),
    item("FEV6_PERCENT", "FEV6 예측치 대비", "PULMONARY", "NUMERIC", "%"),
    item("DENTAL_CARIES", "우식치아", "ORAL", "CODE", allowed_values=["ABSENT", "PRESENT"]),
    item("DENTAL_CARIES_SUSPECTED", "우식의심치아", "ORAL", "CODE", allowed_values=["ABSENT", "PRESENT"]),
    item("DENTAL_RESTORATION", "수복치아", "ORAL", "CODE", allowed_values=["ABSENT", "PRESENT"]),
    item("DENTAL_MISSING", "상실치아", "ORAL", "CODE", allowed_values=["ABSENT", "PRESENT"]),
    item("GINGIVITIS", "치은염증", "ORAL", "CODE", allowed_values=["NONE", "MILD", "SEVERE"]),
    item("CALCULUS", "치석", "ORAL", "CODE", allowed_values=["NONE", "MILD", "SEVERE"]),
    item("PLAQUE_SCORE", "치면세균막검사", "ORAL", "NUMERIC", "score"),
]


def leaf(field: str, op: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


def all_of(*conditions: dict[str, Any]) -> dict[str, Any]:
    return {"all": list(conditions)}


def any_of(*conditions: dict[str, Any]) -> dict[str, Any]:
    return {"any": list(conditions)}


def not_(condition: dict[str, Any]) -> dict[str, Any]:
    return {"not": condition}


def between(field: str, lower: float, upper: float, *, lower_inclusive: bool = True, upper_inclusive: bool = True) -> dict[str, Any]:
    return all_of(
        leaf(field, "gte" if lower_inclusive else "gt", lower),
        leaf(field, "lte" if upper_inclusive else "lt", upper),
    )


RULES: list[dict[str, Any]] = []


def add_rule(
    rule_id: str,
    target: str,
    result_code: str,
    result_label: str,
    normalized_status: str,
    priority: int,
    expression: dict[str, Any],
    locator: str,
    *,
    notes: str | None = None,
) -> None:
    RULES.append(
        {
            "rule_id": rule_id,
            "target_condition": target,
            "result_code": result_code,
            "result_label_original": result_label,
            "normalized_status": normalized_status,
            "severity_rank": {"NORMAL_A": 0, "NORMAL_B": 1, "DISEASE_SUSPECTED": 2, "TREATMENT_REQUIRED": 3}[normalized_status],
            "priority": priority,
            "expression": expression,
            "source_document_code": "MOHW_SCREENING_2026_6_APPENDIX_4_DETAIL",
            "source_locator": locator,
            "notes": notes,
        }
    )


def add_three_band(
    prefix: str,
    target: str,
    field: str,
    normal_expr: dict[str, Any],
    borderline_expr: dict[str, Any],
    suspected_expr: dict[str, Any],
    locator: str,
) -> None:
    add_rule(f"{prefix}_NORMAL_A", target, "NORMAL_A", "정상A", "NORMAL_A", 10, normal_expr, locator)
    add_rule(f"{prefix}_NORMAL_B", target, "NORMAL_B", "정상B(경계)", "NORMAL_B", 20, borderline_expr, locator)
    add_rule(f"{prefix}_SUSPECTED", target, "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, suspected_expr, locator)


# Page 1: general screening thresholds.
add_rule("CHEST_XRAY_NORMAL", "CHEST_DISEASE", "NORMAL_A", "정상", "NORMAL_A", 10, leaf("CHEST_XRAY_RESULT", "eq", "NORMAL"), "별표4의 별첨 1쪽 폐결핵 및 기타흉부질환")
add_rule("CHEST_XRAY_INACTIVE_TB", "CHEST_DISEASE", "NORMAL_B", "비활동성 폐결핵", "NORMAL_B", 20, leaf("CHEST_XRAY_RESULT", "eq", "INACTIVE_TB"), "별표4의 별첨 1쪽 폐결핵 및 기타흉부질환")
add_rule("CHEST_XRAY_OTHER", "CHEST_DISEASE", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, leaf("CHEST_XRAY_RESULT", "eq", "OTHER_ABNORMAL"), "별표4의 별첨 1쪽 폐결핵 및 기타흉부질환", notes="사진불량·미촬영은 판정에서 제외")

add_rule("BP_NORMAL_A", "HYPERTENSION", "NORMAL_A", "정상A", "NORMAL_A", 10, all_of(leaf("SYSTOLIC_BP", "lt", 120), leaf("DIASTOLIC_BP", "lt", 80)), "별표4의 별첨 1쪽 고혈압")
add_rule("BP_NORMAL_B", "HYPERTENSION", "NORMAL_B", "정상B(경계)", "NORMAL_B", 20, all_of(any_of(between("SYSTOLIC_BP", 120, 140, upper_inclusive=False), between("DIASTOLIC_BP", 80, 90, upper_inclusive=False)), not_(any_of(leaf("SYSTOLIC_BP", "gte", 140), leaf("DIASTOLIC_BP", "gte", 90)))), "별표4의 별첨 1쪽 고혈압")
add_rule("BP_SUSPECTED", "HYPERTENSION", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, any_of(leaf("SYSTOLIC_BP", "gte", 140), leaf("DIASTOLIC_BP", "gte", 90)), "별표4의 별첨 1쪽 고혈압")

add_rule("BMI_NORMAL_A", "OBESITY_BMI", "NORMAL_A", "정상A", "NORMAL_A", 10, between("BMI", 18.5, 25, upper_inclusive=False), "별표4의 별첨 1쪽 비만")
add_rule("BMI_LOW", "OBESITY_BMI", "NORMAL_B_LOW", "정상B(저체중)", "NORMAL_B", 20, leaf("BMI", "lt", 18.5), "별표4의 별첨 1쪽 비만")
add_rule("BMI_BORDERLINE", "OBESITY_BMI", "NORMAL_B_HIGH", "정상B(경계)", "NORMAL_B", 20, between("BMI", 25, 30, upper_inclusive=False), "별표4의 별첨 1쪽 비만")
add_rule("BMI_SUSPECTED", "OBESITY_BMI", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, leaf("BMI", "gte", 30), "별표4의 별첨 1쪽 비만")

for sex, cutoff in (("MALE", 90), ("FEMALE", 85)):
    add_rule(f"WAIST_{sex}_NORMAL", "ABDOMINAL_OBESITY", "NORMAL_A", "정상A", "NORMAL_A", 10, all_of(leaf("SUBJECT_SEX", "eq", sex), leaf("WAIST_CIRCUMFERENCE", "lt", cutoff)), "별표4의 별첨 1쪽 허리둘레")
    add_rule(f"WAIST_{sex}_SUSPECTED", "ABDOMINAL_OBESITY", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, all_of(leaf("SUBJECT_SEX", "eq", sex), leaf("WAIST_CIRCUMFERENCE", "gte", cutoff)), "별표4의 별첨 1쪽 허리둘레")

for sex, normal_low, normal_high, border_low in (("MALE", 13.0, 16.5, 12.0), ("FEMALE", 12.0, 15.5, 10.0)):
    add_rule(f"HEMOGLOBIN_{sex}_NORMAL", "ANEMIA", "NORMAL_A", "정상A", "NORMAL_A", 10, all_of(leaf("SUBJECT_SEX", "eq", sex), between("HEMOGLOBIN", normal_low, normal_high)), "별표4의 별첨 1쪽 빈혈")
    add_rule(f"HEMOGLOBIN_{sex}_BORDERLINE", "ANEMIA", "NORMAL_B", "정상B(경계)", "NORMAL_B", 20, all_of(leaf("SUBJECT_SEX", "eq", sex), between("HEMOGLOBIN", border_low, normal_low, upper_inclusive=False)), "별표4의 별첨 1쪽 빈혈")
    add_rule(f"HEMOGLOBIN_{sex}_SUSPECTED", "ANEMIA", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, all_of(leaf("SUBJECT_SEX", "eq", sex), leaf("HEMOGLOBIN", "lt", border_low)), "별표4의 별첨 1쪽 빈혈", notes="원문이 정의하지 않은 상한 초과는 임의 판정하지 않음")

add_three_band("GLUCOSE", "DIABETES", "FASTING_GLUCOSE", leaf("FASTING_GLUCOSE", "lt", 100), between("FASTING_GLUCOSE", 100, 126, upper_inclusive=False), leaf("FASTING_GLUCOSE", "gte", 126), "별표4의 별첨 1쪽 당뇨병")
add_three_band("TOTAL_CHOL", "DYSLIPIDEMIA_TOTAL", "TOTAL_CHOLESTEROL", leaf("TOTAL_CHOLESTEROL", "lt", 200), between("TOTAL_CHOLESTEROL", 200, 240, upper_inclusive=False), leaf("TOTAL_CHOLESTEROL", "gte", 240), "별표4의 별첨 1쪽 이상지질혈증")
add_three_band("HDL", "DYSLIPIDEMIA_HDL", "HDL_CHOLESTEROL", leaf("HDL_CHOLESTEROL", "gte", 60), between("HDL_CHOLESTEROL", 40, 60, upper_inclusive=False), leaf("HDL_CHOLESTEROL", "lt", 40), "별표4의 별첨 1쪽 이상지질혈증 HDL")
add_three_band("TG", "DYSLIPIDEMIA_TG", "TRIGLYCERIDES", leaf("TRIGLYCERIDES", "lt", 150), between("TRIGLYCERIDES", 150, 200, upper_inclusive=False), leaf("TRIGLYCERIDES", "gte", 200), "별표4의 별첨 1쪽 이상지질혈증 중성지방")
add_three_band("LDL", "DYSLIPIDEMIA_LDL", "LDL_CHOLESTEROL", leaf("LDL_CHOLESTEROL", "lt", 130), between("LDL_CHOLESTEROL", 130, 160, upper_inclusive=False), leaf("LDL_CHOLESTEROL", "gte", 160), "별표4의 별첨 1쪽 이상지질혈증 LDL")
add_three_band("AST", "LIVER_AST", "AST", leaf("AST", "lte", 40), between("AST", 40, 50, lower_inclusive=False), leaf("AST", "gt", 50), "별표4의 별첨 1쪽 간장질환 AST")
add_three_band("ALT", "LIVER_ALT", "ALT", leaf("ALT", "lte", 35), between("ALT", 35, 45, lower_inclusive=False), leaf("ALT", "gt", 45), "별표4의 별첨 1쪽 간장질환 ALT")

for sex, normal_low, normal_high, borderline_high in (("MALE", 11, 63, 77), ("FEMALE", 8, 35, 45)):
    add_rule(f"GGT_{sex}_NORMAL", "LIVER_GGT", "NORMAL_A", "정상A", "NORMAL_A", 10, all_of(leaf("SUBJECT_SEX", "eq", sex), between("GAMMA_GTP", normal_low, normal_high)), "별표4의 별첨 1쪽 감마지티피")
    add_rule(f"GGT_{sex}_BORDERLINE", "LIVER_GGT", "NORMAL_B", "정상B(경계)", "NORMAL_B", 20, all_of(leaf("SUBJECT_SEX", "eq", sex), between("GAMMA_GTP", normal_high, borderline_high, lower_inclusive=False)), "별표4의 별첨 1쪽 감마지티피")
    add_rule(f"GGT_{sex}_SUSPECTED", "LIVER_GGT", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, all_of(leaf("SUBJECT_SEX", "eq", sex), leaf("GAMMA_GTP", "gt", borderline_high)), "별표4의 별첨 1쪽 감마지티피", notes="원문이 정의하지 않은 정상범위 하한 미만은 임의 판정하지 않음")

add_rule("URINE_PROTEIN_NEGATIVE", "KIDNEY_URINE_PROTEIN", "NORMAL_A", "음성(-)", "NORMAL_A", 10, leaf("URINE_PROTEIN", "eq", "NEGATIVE"), "별표4의 별첨 1쪽 요단백")
add_rule("URINE_PROTEIN_TRACE", "KIDNEY_URINE_PROTEIN", "NORMAL_B", "약양성(±)", "NORMAL_B", 20, leaf("URINE_PROTEIN", "eq", "TRACE"), "별표4의 별첨 1쪽 요단백")
add_rule("URINE_PROTEIN_POSITIVE", "KIDNEY_URINE_PROTEIN", "DISEASE_SUSPECTED", "양성(+1) 이상", "DISEASE_SUSPECTED", 30, leaf("URINE_PROTEIN", "in", ["POSITIVE_1", "POSITIVE_2", "POSITIVE_3", "POSITIVE_4"]), "별표4의 별첨 1쪽 요단백")
add_rule("CREATININE_NORMAL", "KIDNEY_CREATININE", "NORMAL_A", "정상A", "NORMAL_A", 10, leaf("SERUM_CREATININE", "lte", 1.5), "별표4의 별첨 1쪽 혈청크레아티닌")
add_rule("CREATININE_SUSPECTED", "KIDNEY_CREATININE", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, leaf("SERUM_CREATININE", "gt", 1.5), "별표4의 별첨 1쪽 혈청크레아티닌")
add_rule("EGFR_NORMAL", "KIDNEY_EGFR", "NORMAL_A", "정상A", "NORMAL_A", 10, leaf("EGFR", "gte", 60), "별표4의 별첨 1쪽 e-GFR")
add_rule("EGFR_SUSPECTED", "KIDNEY_EGFR", "DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, leaf("EGFR", "lt", 60), "별표4의 별첨 1쪽 e-GFR")

# Page 2: bone, physical, mental, hearing and pulmonary rules.
add_three_band("BONE_T", "OSTEOPOROSIS_T_SCORE", "BONE_DENSITY_T_SCORE", leaf("BONE_DENSITY_T_SCORE", "gte", -1), between("BONE_DENSITY_T_SCORE", -2.5, -1, lower_inclusive=False, upper_inclusive=False), leaf("BONE_DENSITY_T_SCORE", "lte", -2.5), "별표4의 별첨 2쪽 골다공증 T-score")
add_three_band("BONE_QCT", "OSTEOPOROSIS_PERIPHERAL", "PERIPHERAL_BONE_DENSITY", leaf("PERIPHERAL_BONE_DENSITY", "gt", 120), between("PERIPHERAL_BONE_DENSITY", 80, 120), leaf("PERIPHERAL_BONE_DENSITY", "lt", 80), "별표4의 별첨 2쪽 말단골 골밀도")
add_three_band("LOWER_LIMB", "OLDER_ADULT_LOWER_LIMB", "LOWER_LIMB_FUNCTION_SECONDS", leaf("LOWER_LIMB_FUNCTION_SECONDS", "lte", 10), between("LOWER_LIMB_FUNCTION_SECONDS", 11, 19), leaf("LOWER_LIMB_FUNCTION_SECONDS", "gte", 20), "별표4의 별첨 2쪽 하지기능")
add_three_band("BALANCE_CLOSED", "OLDER_ADULT_BALANCE_CLOSED", "BALANCE_EYES_CLOSED_SECONDS", leaf("BALANCE_EYES_CLOSED_SECONDS", "gte", 15), between("BALANCE_EYES_CLOSED_SECONDS", 6, 14), leaf("BALANCE_EYES_CLOSED_SECONDS", "lte", 5), "별표4의 별첨 2쪽 평형성(눈감은 상태)")
add_three_band("BALANCE_OPEN", "OLDER_ADULT_BALANCE_OPEN", "BALANCE_EYES_OPEN_SECONDS", leaf("BALANCE_EYES_OPEN_SECONDS", "gte", 20), between("BALANCE_EYES_OPEN_SECONDS", 10, 19), leaf("BALANCE_EYES_OPEN_SECONDS", "lte", 9), "별표4의 별첨 2쪽 평형성(눈 뜬 상태)")

add_rule("PHQ9_NONE", "DEPRESSION_SCREEN", "PHQ9_NONE", "우울증상이 없음", "NORMAL_A", 10, between("PHQ9_TOTAL", 0, 4), "별표4의 별첨 2쪽 PHQ-9")
add_rule("PHQ9_MILD", "DEPRESSION_SCREEN", "PHQ9_MILD", "가벼운 우울증상", "NORMAL_B", 20, between("PHQ9_TOTAL", 5, 9), "별표4의 별첨 2쪽 PHQ-9")
add_rule("PHQ9_MODERATE", "DEPRESSION_SCREEN", "PHQ9_MODERATE_SUSPECTED", "중간정도 우울증 의심", "DISEASE_SUSPECTED", 30, between("PHQ9_TOTAL", 10, 19), "별표4의 별첨 2쪽 PHQ-9")
add_rule("PHQ9_SEVERE", "DEPRESSION_SCREEN", "PHQ9_SEVERE_SUSPECTED", "심한 우울증 의심", "DISEASE_SUSPECTED", 40, any_of(leaf("PHQ9_TOTAL", "gte", 20), leaf("PHQ9_ITEM9", "gte", 1)), "별표4의 별첨 2쪽 PHQ-9", notes="9번 문항 1점 이상은 총점과 무관하게 우선 적용")

add_rule("CAPE15_NO_REMARK", "EARLY_PSYCHOSIS_SCREEN", "CAPE15_NO_REMARK", "특이소견 없음", "NORMAL_A", 10, all_of(between("CAPE15_FREQUENCY_TOTAL", 0, 5), between("CAPE15_DISTRESS_TOTAL", 0, 5)), "별표4의 별첨 2쪽 CAPE-15")
add_rule("CAPE15_REFERRAL", "EARLY_PSYCHOSIS_SCREEN", "CAPE15_SPECIALIST_REQUIRED", "전문의 진단 필요", "DISEASE_SUSPECTED", 30, any_of(leaf("CAPE15_FREQUENCY_TOTAL", "gte", 6), leaf("CAPE15_DISTRESS_TOTAL", "gte", 6)), "별표4의 별첨 2쪽 CAPE-15")
add_rule("KDSQC_NO_REMARK", "COGNITIVE_SCREEN", "KDSQC_NO_REMARK", "특이소견 없음", "NORMAL_A", 10, between("KDSQC_TOTAL", 0, 5), "별표4의 별첨 2쪽 KDSQ-C")
add_rule("KDSQC_SUSPECTED", "COGNITIVE_SCREEN", "KDSQC_DECLINE_SUSPECTED", "인지기능 저하 의심", "DISEASE_SUSPECTED", 30, between("KDSQC_TOTAL", 6, 30), "별표4의 별첨 2쪽 KDSQ-C")

add_rule("WHISPER_PASS", "HEARING_WHISPER", "HEARING_PASS", "정상(통과)", "NORMAL_A", 10, all_of(leaf("WHISPER_LEFT_CORRECT", "gte", 3), leaf("WHISPER_RIGHT_CORRECT", "gte", 3)), "별표4의 별첨 2쪽 귓속말 검사")
add_rule("WHISPER_REFERRAL", "HEARING_WHISPER", "HEARING_REFERRAL", "질환의심(의뢰)", "DISEASE_SUSPECTED", 30, any_of(leaf("WHISPER_LEFT_CORRECT", "lt", 3), leaf("WHISPER_RIGHT_CORRECT", "lt", 3)), "별표4의 별첨 2쪽 귓속말 검사")
add_rule("PURE_TONE_PASS", "HEARING_PURE_TONE", "HEARING_PASS", "정상(통과)", "NORMAL_A", 10, leaf("PURE_TONE_DB", "lt", 40), "별표4의 별첨 2쪽 순음청력검사")
add_rule("PURE_TONE_REFERRAL", "HEARING_PURE_TONE", "HEARING_REFERRAL", "질환의심(의뢰)", "DISEASE_SUSPECTED", 30, leaf("PURE_TONE_DB", "gte", 40), "별표4의 별첨 2쪽 순음청력검사")

add_rule("SPIRO_BASIC_NORMAL", "PULMONARY_BASIC", "NORMAL_A", "정상A", "NORMAL_A", 10, all_of(leaf("FEV1_FVC_PERCENT", "gte", 70), leaf("FEV1_PERCENT", "gte", 80), leaf("FVC_PERCENT", "gte", 80)), "별표4의 별첨 2쪽 기본 폐기능검사")
add_rule("SPIRO_BASIC_COPD", "PULMONARY_BASIC", "COPD_SUSPECTED", "만성폐쇄성폐질환의심", "DISEASE_SUSPECTED", 40, leaf("FEV1_FVC_PERCENT", "lt", 70), "별표4의 별첨 2쪽 기본 폐기능검사")
add_rule("SPIRO_BASIC_OTHER", "PULMONARY_BASIC", "OTHER_PULMONARY_ABNORMALITY", "기타 폐기능 이상", "DISEASE_SUSPECTED", 30, all_of(leaf("FEV1_FVC_PERCENT", "gte", 70), any_of(leaf("FEV1_PERCENT", "lt", 80), leaf("FVC_PERCENT", "lt", 80))), "별표4의 별첨 2쪽 기본 폐기능검사")
add_rule("SPIRO_SIMPLE_NORMAL", "PULMONARY_SIMPLE", "NORMAL_A", "정상A", "NORMAL_A", 10, all_of(leaf("FEV1_FEV6_PERCENT", "gte", 73), leaf("FEV1_PERCENT", "gte", 80), leaf("FEV6_PERCENT", "gte", 80)), "별표4의 별첨 2쪽 간이 호흡기능검사")
add_rule("SPIRO_SIMPLE_COPD", "PULMONARY_SIMPLE", "COPD_SUSPECTED", "만성폐쇄성폐질환의심", "DISEASE_SUSPECTED", 40, leaf("FEV1_FEV6_PERCENT", "lt", 73), "별표4의 별첨 2쪽 간이 호흡기능검사")
add_rule("SPIRO_SIMPLE_OTHER", "PULMONARY_SIMPLE", "OTHER_PULMONARY_ABNORMALITY", "기타 폐기능 이상", "DISEASE_SUSPECTED", 30, all_of(leaf("FEV1_FEV6_PERCENT", "gte", 73), any_of(leaf("FEV1_PERCENT", "lt", 80), leaf("FEV6_PERCENT", "lt", 80))), "별표4의 별첨 2쪽 간이 호흡기능검사")

# Page 3: oral screening rules.
for code, label in (("DENTAL_CARIES", "우식치아"), ("DENTAL_CARIES_SUSPECTED", "우식의심치아"), ("DENTAL_RESTORATION", "수복치아"), ("DENTAL_MISSING", "상실치아")):
    add_rule(f"{code}_ABSENT", f"ORAL_{code}", "ORAL_GOOD", "양호", "NORMAL_A", 10, leaf(code, "eq", "ABSENT"), f"별표4의 별첨 3쪽 {label}")

add_rule("DENTAL_CARIES_PRESENT", "ORAL_DENTAL_CARIES", "ORAL_TREATMENT_REQUIRED", "치료필요", "TREATMENT_REQUIRED", 40, leaf("DENTAL_CARIES", "eq", "PRESENT"), "별표4의 별첨 3쪽 우식치아")
add_rule("DENTAL_CARIES_SUSPECTED_PRESENT", "ORAL_DENTAL_CARIES_SUSPECTED", "ORAL_DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, leaf("DENTAL_CARIES_SUSPECTED", "eq", "PRESENT"), "별표4의 별첨 3쪽 우식의심치아")
add_rule("DENTAL_RESTORATION_PRESENT", "ORAL_DENTAL_RESTORATION", "ORAL_CAUTION", "주의", "NORMAL_B", 20, leaf("DENTAL_RESTORATION", "eq", "PRESENT"), "별표4의 별첨 3쪽 수복치아")
add_rule("DENTAL_MISSING_PRESENT", "ORAL_DENTAL_MISSING", "ORAL_TREATMENT_REQUIRED", "치료필요", "TREATMENT_REQUIRED", 40, leaf("DENTAL_MISSING", "eq", "PRESENT"), "별표4의 별첨 3쪽 상실치아")

for code, label in (("GINGIVITIS", "치은염증"), ("CALCULUS", "치석")):
    add_rule(f"{code}_NONE", f"ORAL_{code}", "ORAL_GOOD", "양호", "NORMAL_A", 10, leaf(code, "eq", "NONE"), f"별표4의 별첨 3쪽 {label}")
    add_rule(f"{code}_MILD", f"ORAL_{code}", "ORAL_DISEASE_SUSPECTED", "질환의심", "DISEASE_SUSPECTED", 30, leaf(code, "eq", "MILD"), f"별표4의 별첨 3쪽 {label}")
    add_rule(f"{code}_SEVERE", f"ORAL_{code}", "ORAL_TREATMENT_REQUIRED", "치료필요", "TREATMENT_REQUIRED", 40, leaf(code, "eq", "SEVERE"), f"별표4의 별첨 3쪽 {label}")

add_rule("PLAQUE_GOOD", "ORAL_PLAQUE", "ORAL_GOOD", "우수", "NORMAL_A", 10, leaf("PLAQUE_SCORE", "lt", 1), "별표4의 별첨 3쪽 치면세균막검사")
add_rule("PLAQUE_CAUTION", "ORAL_PLAQUE", "ORAL_CAUTION", "보통", "NORMAL_B", 20, between("PLAQUE_SCORE", 1, 3, upper_inclusive=False), "별표4의 별첨 3쪽 치면세균막검사")
add_rule("PLAQUE_SUSPECTED", "ORAL_PLAQUE", "ORAL_DISEASE_SUSPECTED", "개선요망", "DISEASE_SUSPECTED", 30, leaf("PLAQUE_SCORE", "gte", 3), "별표4의 별첨 3쪽 치면세균막검사")


ELIGIBILITY = [
    {"component_code": "GENERAL_BASE", "display_name_ko": "문진·진찰·신체계측·혈압·시력·청력", "eligibility": {"all_screening_subjects": True}, "interval": "검진 대상 주기", "source_locator": "별표1 1쪽"},
    {"component_code": "CHEST_XRAY", "display_name_ko": "흉부방사선 촬영", "eligibility": {"all_screening_subjects": True}, "interval": "검진 대상 주기", "source_locator": "별표1 1쪽"},
    {"component_code": "URINE_PROTEIN", "display_name_ko": "요단백", "eligibility": {"all_screening_subjects": True}, "interval": "검진 대상 주기", "source_locator": "별표1 2쪽"},
    {"component_code": "CORE_BLOOD_TESTS", "display_name_ko": "혈색소·공복혈당·간·신장 검사", "eligibility": {"all_screening_subjects": True}, "interval": "검진 대상 주기", "source_locator": "별표1 2쪽"},
    {"component_code": "LIPID_PANEL", "display_name_ko": "콜레스테롤 4종", "eligibility": {"any": [{"all": [{"sex": "MALE"}, {"age_gte": 24}]}, {"all": [{"sex": "FEMALE"}, {"age_gte": 40}]}]}, "interval": "4년마다", "source_locator": "별표1 2쪽"},
    {"component_code": "HEPATITIS_B", "display_name_ko": "B형간염 표면항원·항체", "eligibility": {"age_eq": 40, "exclusions": ["기존 표면항원 양성", "자동·피동면역 항체형성"]}, "interval": "해당 연령", "source_locator": "별표1 3쪽"},
    {"component_code": "HEPATITIS_C", "display_name_ko": "C형간염 항체", "eligibility": {"age_eq": 56}, "interval": "해당 연령", "source_locator": "별표1 3쪽"},
    {"component_code": "BONE_DENSITY", "display_name_ko": "골밀도 검사", "eligibility": {"sex": "FEMALE", "age_in": [54, 60, 66]}, "interval": "해당 연령", "source_locator": "별표1 3쪽"},
    {"component_code": "PULMONARY_FUNCTION", "display_name_ko": "폐기능 검사", "eligibility": {"age_in": [56, 66]}, "interval": "해당 연령", "source_locator": "별표1 3-4쪽"},
    {"component_code": "KDSQC", "display_name_ko": "인지기능장애 KDSQ-C", "eligibility": {"age_gte": 66}, "interval": "2년마다", "source_locator": "별표1 4쪽"},
    {"component_code": "LIFESTYLE_ASSESSMENT", "display_name_ko": "생활습관평가", "eligibility": {"age_in": [40, 50, 60, 70]}, "interval": "해당 연령", "source_locator": "별표1 4쪽"},
    {"component_code": "PHQ9", "display_name_ko": "정신건강검사 PHQ-9", "eligibility": {"age_rules": [{"age_range": [20, 34], "interval": "2년마다"}, {"age_range": [35, 39], "interval": "1회"}, {"age_range": [40, 49], "interval": "1회"}, {"age_range": [50, 59], "interval": "1회"}, {"age_range": [60, 69], "interval": "1회"}, {"age_range": [70, 79], "interval": "1회"}]}, "interval": "연령별", "source_locator": "별표1 5쪽"},
    {"component_code": "CAPE15", "display_name_ko": "정신건강검사 CAPE-15", "eligibility": {"age_range": [20, 34]}, "interval": "2년마다", "source_locator": "별표1 5쪽"},
    {"component_code": "OLDER_ADULT_FUNCTION", "display_name_ko": "노인신체기능검사", "eligibility": {"age_in": [66, 70, 80]}, "interval": "해당 연령", "source_locator": "별표1 5-6쪽"},
    {"component_code": "ORAL_SCREENING", "display_name_ko": "구강검진", "eligibility": {"all_screening_subjects": True}, "interval": "검진 대상 주기", "source_locator": "별표1 6쪽"},
    {"component_code": "PLAQUE_TEST", "display_name_ko": "치면세균막검사", "eligibility": {"age_eq": 40}, "interval": "해당 연령", "source_locator": "별표1 6쪽"},
]


BOUNDARY_CASES = [
    {"id": "glucose_99", "target": "DIABETES", "values": {"FASTING_GLUCOSE": 99}, "expected": "NORMAL_A"},
    {"id": "glucose_100", "target": "DIABETES", "values": {"FASTING_GLUCOSE": 100}, "expected": "NORMAL_B"},
    {"id": "glucose_125", "target": "DIABETES", "values": {"FASTING_GLUCOSE": 125}, "expected": "NORMAL_B"},
    {"id": "glucose_126", "target": "DIABETES", "values": {"FASTING_GLUCOSE": 126}, "expected": "DISEASE_SUSPECTED"},
    {"id": "bp_normal", "target": "HYPERTENSION", "values": {"SYSTOLIC_BP": 119, "DIASTOLIC_BP": 79}, "expected": "NORMAL_A"},
    {"id": "bp_border_diastolic", "target": "HYPERTENSION", "values": {"SYSTOLIC_BP": 119, "DIASTOLIC_BP": 80}, "expected": "NORMAL_B"},
    {"id": "bp_suspected_systolic", "target": "HYPERTENSION", "values": {"SYSTOLIC_BP": 140, "DIASTOLIC_BP": 79}, "expected": "DISEASE_SUSPECTED"},
    {"id": "hdl_39", "target": "DYSLIPIDEMIA_HDL", "values": {"HDL_CHOLESTEROL": 39}, "expected": "DISEASE_SUSPECTED"},
    {"id": "hdl_40", "target": "DYSLIPIDEMIA_HDL", "values": {"HDL_CHOLESTEROL": 40}, "expected": "NORMAL_B"},
    {"id": "hdl_60", "target": "DYSLIPIDEMIA_HDL", "values": {"HDL_CHOLESTEROL": 60}, "expected": "NORMAL_A"},
    {"id": "phq_item9_override", "target": "DEPRESSION_SCREEN", "values": {"PHQ9_TOTAL": 8, "PHQ9_ITEM9": 1}, "expected": "PHQ9_SEVERE_SUSPECTED"},
    {"id": "cape_distress_override", "target": "EARLY_PSYCHOSIS_SCREEN", "values": {"CAPE15_FREQUENCY_TOTAL": 2, "CAPE15_DISTRESS_TOTAL": 6}, "expected": "CAPE15_SPECIALIST_REQUIRED"},
    {"id": "hearing_one_ear_fail", "target": "HEARING_WHISPER", "values": {"WHISPER_LEFT_CORRECT": 3, "WHISPER_RIGHT_CORRECT": 2}, "expected": "HEARING_REFERRAL"},
    {"id": "spiro_basic_copd", "target": "PULMONARY_BASIC", "values": {"FEV1_FVC_PERCENT": 69, "FEV1_PERCENT": 90, "FVC_PERCENT": 90}, "expected": "COPD_SUSPECTED"},
    {"id": "spiro_basic_other", "target": "PULMONARY_BASIC", "values": {"FEV1_FVC_PERCENT": 70, "FEV1_PERCENT": 79, "FVC_PERCENT": 90}, "expected": "OTHER_PULMONARY_ABNORMALITY"},
    {"id": "plaque_1", "target": "ORAL_PLAQUE", "values": {"PLAQUE_SCORE": 1}, "expected": "ORAL_CAUTION"},
    {"id": "plaque_3", "target": "ORAL_PLAQUE", "values": {"PLAQUE_SCORE": 3}, "expected": "ORAL_DISEASE_SUSPECTED"},
]


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", value).lower()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_pdf_pages(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def expression_fields(expression: dict[str, Any]) -> set[str]:
    if "field" in expression:
        return {expression["field"]}
    fields: set[str] = set()
    for key in ("all", "any"):
        for child in expression.get(key, []):
            fields.update(expression_fields(child))
    if "not" in expression:
        fields.update(expression_fields(expression["not"]))
    return fields


def evaluate_expression(expression: dict[str, Any], values: dict[str, Any]) -> bool:
    if "all" in expression:
        return all(evaluate_expression(child, values) for child in expression["all"])
    if "any" in expression:
        return any(evaluate_expression(child, values) for child in expression["any"])
    if "not" in expression:
        return not evaluate_expression(expression["not"], values)

    field = expression["field"]
    if field not in values or values[field] is None:
        return False
    actual = values[field]
    expected = expression["value"]
    op = expression["op"]
    return {
        "eq": lambda: actual == expected,
        "in": lambda: actual in expected,
        "lt": lambda: actual < expected,
        "lte": lambda: actual <= expected,
        "gt": lambda: actual > expected,
        "gte": lambda: actual >= expected,
    }[op]()


def evaluate_target(target: str, values: dict[str, Any]) -> dict[str, Any] | None:
    matches = [
        rule
        for rule in RULES
        if rule["target_condition"] == target
        and evaluate_expression(rule["expression"], values)
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: (row["priority"], row["severity_rank"]))


def verify_documents() -> tuple[list[dict[str, Any]], list[str]]:
    documents: list[dict[str, Any]] = []
    errors: list[str] = []
    for source in DOCUMENTS:
        path = source["path"]
        if not path.exists():
            errors.append(f"missing source PDF: {path}")
            continue
        actual_sha = sha256(path)
        if actual_sha != source["sha256"]:
            errors.append(f"checksum mismatch: {path.name}: {actual_sha}")
        pages = read_pdf_pages(path)
        if len(pages) != source["page_count"]:
            errors.append(
                f"page count mismatch: {path.name}: {len(pages)} != {source['page_count']}"
            )
        anchor_results = []
        for page_no, anchors in source["page_anchors"].items():
            page_text = normalize_text(pages[page_no - 1]) if page_no <= len(pages) else ""
            missing = [anchor for anchor in anchors if normalize_text(anchor) not in page_text]
            anchor_results.append(
                {"page": page_no, "anchors": anchors, "missing": missing, "passed": not missing}
            )
            if missing:
                errors.append(f"missing anchors: {path.name} page {page_no}: {missing}")
        documents.append(
            {
                key: (str(value.relative_to(ROOT)) if key == "path" else value)
                for key, value in source.items()
                if key != "page_anchors"
            }
            | {"actual_sha256": actual_sha, "anchor_checks": anchor_results}
        )
    return documents, errors


def validate_rules() -> list[str]:
    errors: list[str] = []
    item_codes = [row["item_code"] for row in ITEMS]
    if len(item_codes) != len(set(item_codes)):
        errors.append("duplicate item_code")
    rule_ids = [row["rule_id"] for row in RULES]
    if len(rule_ids) != len(set(rule_ids)):
        errors.append("duplicate rule_id")
    result_definition_codes = [row["result_code"] for row in RESULT_DEFINITIONS]
    if len(result_definition_codes) != len(set(result_definition_codes)):
        errors.append("duplicate result definition code")
    known = set(item_codes)
    for rule in RULES:
        missing = expression_fields(rule["expression"]) - known
        if missing:
            errors.append(f"{rule['rule_id']} references unknown fields: {sorted(missing)}")
        if not rule["source_locator"]:
            errors.append(f"{rule['rule_id']} has no source locator")
    for case in BOUNDARY_CASES:
        match = evaluate_target(case["target"], case["values"])
        actual = match["result_code"] if match else None
        if actual != case["expected"]:
            errors.append(f"boundary {case['id']}: {actual} != {case['expected']}")
    return errors


def rule_type(expression: dict[str, Any]) -> str:
    return "ATOMIC" if "field" in expression else "COMPOSITE"


def build_dataset(documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "regulation": {
            "title": "건강검진 실시기준",
            "notice": "보건복지부고시 제2026-6호",
            "effective_from": "2026-01-07",
            "jurisdiction": "KR",
            "scope": "일반건강검진 및 의료급여생애전환기검진",
            "usage_warning": "국가건강검진 판정용이며 진단기준 또는 검사실 참고범위로 재사용하지 않음",
        },
        "documents": documents,
        "result_definitions": RESULT_DEFINITIONS,
        "items": ITEMS,
        "eligibility": ELIGIBILITY,
        "rules": [dict(rule, rule_type=rule_type(rule["expression"])) for rule in RULES],
        "boundary_cases": BOUNDARY_CASES,
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


def render_artifacts(dataset: dict[str, Any], errors: list[str]) -> dict[str, str]:
    items_fields = ["item_code", "display_name_ko", "domain", "value_type", "canonical_unit", "integer_only", "allowed_values"]
    rule_fields = ["rule_id", "rule_type", "target_condition", "result_code", "result_label_original", "normalized_status", "severity_rank", "priority", "expression", "source_document_code", "source_locator", "notes"]
    eligibility_fields = ["component_code", "display_name_ko", "eligibility", "interval", "source_locator"]
    atomic_count = sum(1 for row in dataset["rules"] if row["rule_type"] == "ATOMIC")
    quality = {
        "status": "PASS" if not errors else "FAIL",
        "dataset": {
            "document_count": len(dataset["documents"]),
            "item_count": len(dataset["items"]),
            "rule_count": len(dataset["rules"]),
            "atomic_rule_count": atomic_count,
            "composite_rule_count": len(dataset["rules"]) - atomic_count,
            "eligibility_count": len(dataset["eligibility"]),
            "boundary_case_count": len(dataset["boundary_cases"]),
        },
        "checks": {
            "source_checksums": all(doc["actual_sha256"] == doc["sha256"] for doc in dataset["documents"]),
            "source_page_anchors": all(check["passed"] for doc in dataset["documents"] for check in doc["anchor_checks"]),
            "unique_item_codes": len({row["item_code"] for row in ITEMS}) == len(ITEMS),
            "unique_rule_ids": len({row["rule_id"] for row in RULES}) == len(RULES),
            "boundary_cases": not any(error.startswith("boundary ") for error in errors),
        },
        "errors": errors,
        "known_limitations": [
            "표 병합과 복합 조건 때문에 원문 표를 무검수 자동 변환하지 않고 시각 검수된 규칙 사양을 사용함",
            "정수 구간으로 제시된 노인신체기능 검사는 소수 입력을 판정하지 않음",
            "원문이 정의하지 않은 혈색소 상한 초과와 감마지티피 하한 미만은 임의 판정하지 않음",
            "규칙은 건강검진 판정이며 질병 진단 또는 치료 결정을 의미하지 않음",
        ],
    }
    return {
        DATASET_JSON: json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        ITEMS_CSV: csv_text(dataset["items"], items_fields),
        RULES_CSV: csv_text(dataset["rules"], rule_fields),
        ELIGIBILITY_CSV: csv_text(dataset["eligibility"], eligibility_fields),
        QUALITY_JSON: json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
    }


def write_or_check(artifacts: dict[str, str], output_dir: Path, check: bool) -> list[str]:
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
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--check", action="store_true", help="verify generated artifacts are synchronized")
    args = parser.parse_args()

    documents, source_errors = verify_documents()
    rule_errors = validate_rules()
    dataset = build_dataset(documents)
    errors = source_errors + rule_errors
    artifacts = render_artifacts(dataset, errors)
    sync_errors = write_or_check(artifacts, args.output_dir, args.check)
    errors.extend(sync_errors)

    summary = {
        "status": "PASS" if not errors else "FAIL",
        "documents": len(documents),
        "items": len(ITEMS),
        "rules": len(RULES),
        "eligibility": len(ELIGIBILITY),
        "boundary_cases": len(BOUNDARY_CASES),
        "output_dir": str(args.output_dir),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
