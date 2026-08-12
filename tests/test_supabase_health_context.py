"""Supabase 사용자 건강검진 컨텍스트 조회 테스트.

작성자: 김진우
"""

import unittest
from unittest.mock import Mock, patch

from app.services.supabase_health_context import SupabaseHealthContextService


def _response(payload) -> Mock:
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = payload
    return response


class SupabaseHealthContextServiceTest(unittest.TestCase):
    def test_resolved_screening_terms_select_requested_catalog_item(self) -> None:
        catalog = (
            {
                "item_code": "HDL_CHOLESTEROL",
                "item_name": "고밀도(HDL) 콜레스테롤",
                "standard_unit": "mg/dL",
            },
            {
                "item_code": "LDL_CHOLESTEROL",
                "item_name": "저밀도(LDL) 콜레스테롤",
                "standard_unit": "mg/dL",
            },
        )

        for acronym, expected_code in (
            ("HDL", "HDL_CHOLESTEROL"),
            ("LDL", "LDL_CHOLESTEROL"),
        ):
            with self.subTest(acronym=acronym):
                selected, _, _ = SupabaseHealthContextService._select_item_codes(
                    f"나의 {acronym} 수치가 어떤 편이야?",
                    catalog,
                    (
                        {
                            "canonical_key": expected_code,
                            "canonical_name": f"{acronym} 콜레스테롤",
                            "term_type": "SCREENING",
                            "matched_alias": acronym,
                            "canonical_keys": [expected_code],
                        },
                    ),
                )
                self.assertEqual(selected, {expected_code})

    def test_all_resolved_catalog_codes_use_the_same_selection_rule(self) -> None:
        catalog = tuple(
            {
                "item_code": code,
                "item_name": name,
                "standard_unit": unit,
            }
            for code, name, unit in (
                ("AST", "에이에스티(AST)", "U/L"),
                ("EGFR", "신사구체여과율(e-GFR)", "mL/min"),
                ("FASTING_GLUCOSE", "공복혈당", "mg/dL"),
                ("HDL_CHOLESTEROL", "고밀도(HDL) 콜레스테롤", "mg/dL"),
                ("LDL_CHOLESTEROL", "저밀도(LDL) 콜레스테롤", "mg/dL"),
                ("WAIST_CIRCUMFERENCE", "허리둘레", "cm"),
            )
        )
        resolved_terms = tuple(
            {
                "canonical_key": item["item_code"],
                "canonical_name": item["item_name"],
                "term_type": "SCREENING",
                "canonical_keys": [item["item_code"]],
            }
            for item in catalog
        )

        selected, _, _ = SupabaseHealthContextService._select_item_codes(
            "내 검사항목들을 알려줘",
            catalog,
            resolved_terms,
        )

        self.assertEqual(
            selected,
            {str(item["item_code"]) for item in catalog},
        )

    def test_alias_group_uses_all_canonical_keys_from_term_dictionary(self) -> None:
        catalog = tuple(
            {
                "item_code": code,
                "item_name": code,
                "standard_unit": "U/L",
            }
            for code in ("AST", "ALT", "GAMMA_GTP")
        )

        selected, _, _ = SupabaseHealthContextService._select_item_codes(
            "내 간수치를 알려줘",
            catalog,
            (
                {
                    "canonical_key": "ALIAS_GROUP:간수치",
                    "canonical_name": "간수치",
                    "term_type": "ALIAS_GROUP",
                    "matched_alias": "간수치",
                    "canonical_keys": ["AST", "ALT", "GAMMA_GTP"],
                },
            ),
        )

        self.assertEqual(selected, {"AST", "ALT", "GAMMA_GTP"})

    def test_non_screening_medical_term_does_not_select_checkup_item(self) -> None:
        catalog = (
            {
                "item_code": "SYSTOLIC_BP",
                "item_name": "수축기 혈압",
                "standard_unit": "mmHg",
            },
        )

        selected, _, _ = SupabaseHealthContextService._select_item_codes(
            "나 고혈압이 뭐야?",
            catalog,
            (
                {
                    "canonical_key": "HYPERTENSION",
                    "canonical_name": "고혈압",
                    "term_type": "DISEASE",
                    "matched_alias": "혈압",
                    "canonical_keys": ["HYPERTENSION"],
                },
            ),
        )

        self.assertEqual(selected, set())

    def test_abnormal_value_question_selects_latest_non_normal_results(self) -> None:
        selected, generic_checkup, non_normal_only = (
            SupabaseHealthContextService._select_item_codes(
                "내 검진 결과에서 서로 연관지어 볼 만한 이상 수치가 있어?",
                (),
            )
        )

        self.assertEqual(selected, set())
        self.assertTrue(generic_checkup)
        self.assertTrue(non_normal_only)

    @patch("app.services.supabase_health_context.requests.get")
    def test_explicit_item_fetches_only_latest_relevant_result(self, get: Mock) -> None:
        get.side_effect = [
            _response(
                [
                    {
                        "item_code": "AST",
                        "item_name": "에이에스티(AST)",
                        "standard_unit": "U/L",
                    },
                    {
                        "item_code": "ALT",
                        "item_name": "에이엘티(ALT)",
                        "standard_unit": "U/L",
                    },
                ]
            ),
            _response(
                [
                    {
                        "name": "김민철",
                        "birth_date": "1985-04-18",
                        "sex": "Male",
                        "chronic_conditions": ["고혈압"],
                    }
                ]
            ),
            _response(
                [
                    {"record_id": "latest", "measured_at": "2026-08-06"},
                    {"record_id": "old", "measured_at": "2024-07-18"},
                ]
            ),
            _response(
                [
                    {
                        "result_id": "result",
                        "record_id": "latest",
                        "item_code": "AST",
                        "value": "54",
                        "status": "이상",
                    }
                ]
            ),
        ]
        service = SupabaseHealthContextService("https://example.supabase.co", "key")

        context = service.get_relevant_context(
            "access-token",
            "user-id",
            "내 AST 수치가 어떤지 알려줘",
        )

        self.assertIsNotNone(context)
        self.assertEqual(context.item_codes, ("AST",))
        self.assertFalse(context.includes_history)
        self.assertIn("2026-08-06", context.prompt_text)
        self.assertIn("54 U/L", context.prompt_text)
        self.assertIn("DB 상태: 이상", context.prompt_text)
        result_url = get.call_args_list[-1].args[0]
        self.assertIn("record_id=in.(latest)", result_url)
        self.assertIn("item_code=in.(AST)", result_url)
        self.assertNotIn("old", result_url)

    @patch("app.services.supabase_health_context.requests.get")
    def test_unrelated_question_does_not_read_personal_results(self, get: Mock) -> None:
        get.return_value = _response(
            [
                {
                    "item_code": "AST",
                    "item_name": "에이에스티(AST)",
                    "standard_unit": "U/L",
                }
            ]
        )
        service = SupabaseHealthContextService("https://example.supabase.co", "key")

        context = service.get_relevant_context(
            "access-token",
            "user-id",
            "감기에 걸린 것 같은데 어떻게 해야 해?",
        )

        self.assertIsNone(context)
        self.assertEqual(get.call_count, 1)

    @patch("app.services.supabase_health_context.requests.get")
    def test_hdl_acronym_fetches_only_hdl_cholesterol_result(self, get: Mock) -> None:
        get.side_effect = [
            _response(
                [
                    {
                        "item_code": "HDL_CHOLESTEROL",
                        "item_name": "고밀도(HDL) 콜레스테롤",
                        "standard_unit": "mg/dL",
                    },
                    {
                        "item_code": "LDL_CHOLESTEROL",
                        "item_name": "저밀도(LDL) 콜레스테롤",
                        "standard_unit": "mg/dL",
                    },
                ]
            ),
            _response([{"name": "김민철", "chronic_conditions": ["고혈압"]}]),
            _response([{"record_id": "latest", "measured_at": "2026-08-06"}]),
            _response(
                [
                    {
                        "result_id": "hdl-result",
                        "record_id": "latest",
                        "item_code": "HDL_CHOLESTEROL",
                        "value": "45",
                        "status": "정상",
                    }
                ]
            ),
        ]
        service = SupabaseHealthContextService("https://example.supabase.co", "key")

        context = service.get_relevant_context(
            "access-token",
            "user-id",
            "나의 HDL 콜레스테롤 수치가 어떤 편이야?",
            (
                {
                    "canonical_key": "HDL_CHOLESTEROL",
                    "canonical_name": "HDL 콜레스테롤",
                    "term_type": "SCREENING",
                    "matched_alias": "HDL",
                    "canonical_keys": ["HDL_CHOLESTEROL"],
                },
            ),
        )

        self.assertIsNotNone(context)
        self.assertEqual(context.item_codes, ("HDL_CHOLESTEROL",))
        self.assertIn("45 mg/dL", context.prompt_text)
        result_url = get.call_args_list[-1].args[0]
        self.assertIn("item_code=in.(HDL_CHOLESTEROL)", result_url)
        self.assertNotIn("LDL_CHOLESTEROL", result_url)


if __name__ == "__main__":
    unittest.main()
