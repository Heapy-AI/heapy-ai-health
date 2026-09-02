"""Supabase 사용자 생활습관 컨텍스트 조회 테스트.

작성자: 고수연
"""

import unittest
from unittest.mock import Mock, patch

from app.services.supabase_conversation import SupabaseConversationError
from app.services.supabase_lifestyle_context import SupabaseLifestyleContextService


def _service() -> SupabaseLifestyleContextService:
    return SupabaseLifestyleContextService(
        "https://example.supabase.co",
        "publishable-key",
        max_rows=5,
        trend_max_rows=20,
    )


def _response(payload) -> Mock:
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = payload
    return response


class SelectDomainsTest(unittest.TestCase):
    def test_activity_question_selects_activity_only(self) -> None:
        domains, bio_types = SupabaseLifestyleContextService._select_domains(
            "내 걸음수 요즘 어때?"
        )
        self.assertEqual(domains, {"activity"})
        self.assertEqual(bio_types, set())

    def test_bio_question_selects_matching_bio_type(self) -> None:
        for question, expected in (
            ("내 체중 어때?", "weight"),
            ("내 혈압 정상이야?", "blood_pressure"),
            ("내 혈당 괜찮아?", "blood_glucose"),
            ("내 수면시간 충분해?", "sleep"),
            ("내 심박수 높은 편이야?", "heart_rate"),
            ("내 BMI 알려줘", "bmi"),
        ):
            with self.subTest(question=question):
                domains, bio_types = (
                    SupabaseLifestyleContextService._select_domains(question)
                )
                self.assertIn("bio", domains)
                self.assertEqual(bio_types, {expected})

    def test_generic_question_selects_every_domain(self) -> None:
        domains, bio_types = SupabaseLifestyleContextService._select_domains(
            "내 생활습관 전반적으로 어때?"
        )
        self.assertEqual(domains, {"activity", "exercise", "nutrition", "bio"})
        self.assertEqual(bio_types, set())

    def test_unrelated_question_selects_nothing(self) -> None:
        domains, bio_types = SupabaseLifestyleContextService._select_domains(
            "고혈압은 어떤 질병이야?"
        )
        self.assertEqual(domains, set())
        self.assertEqual(bio_types, set())

    def test_disease_names_do_not_select_the_metric_they_contain(self) -> None:
        """일반 질병 질문이 개인 지표 조회를 유발하지 않아야 한다."""
        for question in (
            "고혈압은 어떤 질병이야?",
            "저혈압도 위험해?",
            "당뇨병 초기 증상 알려줘",
            "당뇨 관리 방법이 뭐야?",
            "고혈당이면 어떻게 해야 해?",
            "저혈당 응급처치 알려줘",
            "수면무호흡증은 왜 생겨?",
            "수면장애 치료법 알려줘",
            "지방간에 좋은 음식 말고 원인이 뭐야?",
        ):
            with self.subTest(question=question):
                domains, _ = SupabaseLifestyleContextService._select_domains(question)
                self.assertNotIn("bio", domains)

    def test_metric_word_still_selects_after_disease_filtering(self) -> None:
        """질병명 제거가 정상적인 지표 질문을 막지 않아야 한다."""
        for question, expected in (
            ("내 혈압 어때?", "blood_pressure"),
            ("내 혈당 수치 알려줘", "blood_glucose"),
            ("내 수면 시간 어때?", "sleep"),
        ):
            with self.subTest(question=question):
                domains, bio_types = (
                    SupabaseLifestyleContextService._select_domains(question)
                )
                self.assertIn("bio", domains)
                self.assertEqual(bio_types, {expected})

    def test_resolved_terms_contribute_to_domain_selection(self) -> None:
        domains, _ = SupabaseLifestyleContextService._select_domains(
            "이거 어때?",
            (
                {
                    "canonical_name": "수면",
                    "matched_alias": "잠",
                },
            ),
        )
        self.assertIn("bio", domains)


class GetRelevantContextTest(unittest.TestCase):
    def test_unrelated_question_skips_every_request(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get"
        ) as mocked_get:
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "당뇨병 합병증 알려줘 아니라 일반 질문",
            )
        self.assertIsNone(context)
        mocked_get.assert_not_called()

    def test_missing_access_token_returns_none(self) -> None:
        self.assertIsNone(
            _service().get_relevant_context("", "user-1", "내 걸음수 어때?")
        )

    def test_activity_question_requests_only_activity_table(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "record_date": "2026-08-19",
                        "steps": 8123,
                        "floors_climbed": 3,
                        "active_time": 42,
                        "active_distance": 6.58,
                        "active_calories": 210,
                    }
                ]
            ),
        ) as mocked_get:
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 걸음수 요즘 어때?",
            )

        self.assertIsNotNone(context)
        self.assertEqual(context.domains, ("activity",))
        self.assertEqual(context.record_count, 1)
        self.assertFalse(context.includes_history)
        self.assertIn("[인증된 사용자 생활습관 정보]", context.prompt_text)
        self.assertIn("걸음 8,123보", context.prompt_text)
        self.assertIn("2026-08-19", context.prompt_text)
        # active_distance는 km 단위로 적재되므로 환산 없이 km로 표기한다.
        self.assertIn("이동 6.6km", context.prompt_text)

        self.assertEqual(mocked_get.call_count, 1)
        url = mocked_get.call_args.args[0]
        self.assertIn("/rest/v1/lifestyle_activity", url)
        self.assertIn("user_id=eq.user-1", url)
        self.assertIn("order=record_date.desc", url)
        self.assertIn("limit=5", url)

    def test_request_sends_user_token_and_publishable_key(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response([{"record_date": "2026-08-19", "steps": 1}]),
        ) as mocked_get:
            _service().get_relevant_context("user-token", "user-1", "내 걸음수 어때?")

        headers = mocked_get.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer user-token")
        self.assertEqual(headers["apikey"], "publishable-key")

    def test_trend_question_uses_trend_row_limit(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response([{"record_date": "2026-08-19", "steps": 1}]),
        ) as mocked_get:
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 걸음수 추이 알려줘",
            )

        self.assertTrue(context.includes_history)
        self.assertIn("limit=20", mocked_get.call_args.args[0])

    def test_bio_question_requests_one_call_per_selected_type(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "measured_at": "2026-08-19T07:10:00",
                        "bio_type": "weight",
                        "value": 71.25,
                        "unit": "kg",
                    }
                ]
            ),
        ) as mocked_get:
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 체중이랑 혈압 어때?",
            )

        self.assertEqual(context.bio_types, ("blood_pressure", "weight"))
        self.assertEqual(mocked_get.call_count, 2)
        requested_types = sorted(
            call.args[0].split("bio_type=eq.")[1].split("&")[0]
            for call in mocked_get.call_args_list
        )
        self.assertEqual(requested_types, ["blood_pressure", "weight"])
        self.assertIn("체중 | 71.2 kg", context.prompt_text)

    def test_blood_pressure_shows_systolic_and_diastolic(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "measured_at": "2026-08-18T08:00:00",
                        "bio_type": "blood_pressure",
                        "value": 133.2,
                        "unit": "mmHg",
                        "detail_data": {
                            "pulse": 69,
                            "systolic": 133,
                            "diastolic": 84,
                        },
                    }
                ]
            ),
        ):
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 혈압 어때?",
            )

        self.assertIn("혈압 | 133/84 mmHg | 맥박 69bpm", context.prompt_text)

    def test_blood_glucose_marks_fasting_state(self) -> None:
        for fasting, expected in ((True, "공복"), (False, "식후")):
            with self.subTest(fasting=fasting):
                with patch(
                    "app.services.supabase_lifestyle_context.requests.get",
                    return_value=_response(
                        [
                            {
                                "measured_at": "2026-08-17T07:30:00",
                                "bio_type": "blood_glucose",
                                "value": 101.3,
                                "unit": "mg/dL",
                                "detail_data": {"fasting": fasting},
                            }
                        ]
                    ),
                ):
                    context = _service().get_relevant_context(
                        "token",
                        "user-1",
                        "내 혈당 어때?",
                    )
                self.assertIn(f"101.3 mg/dL | {expected}", context.prompt_text)

    def test_sleep_unit_is_localized_and_stages_included(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "measured_at": "2026-08-19T07:10:00",
                        "bio_type": "sleep",
                        "value": 6.21,
                        "unit": "hour",
                        "detail_data": {
                            "awake_min": 31,
                            "sleep_score": 74,
                            "deep_sleep_min": 78,
                        },
                    }
                ]
            ),
        ):
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 수면 어때?",
            )

        self.assertIn(
            "수면시간 | 6.2 시간 | 수면점수 74 | 깊은수면 78분 | 깬시간 31분",
            context.prompt_text,
        )

    def test_null_detail_data_is_tolerated(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "measured_at": "2026-08-19T07:00:00",
                        "bio_type": "weight",
                        "value": 79.4,
                        "unit": "kg",
                        "detail_data": None,
                    }
                ]
            ),
        ):
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 체중 어때?",
            )

        self.assertIn("체중 | 79.4 kg", context.prompt_text)

    def test_exercise_distance_in_meters_is_converted_to_km(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "record_date": "2026-08-18T00:00:00",
                        "exercise_type": "walking",
                        "duration_sec": 2640,
                        "distance_m": 4150,
                        "calories": 284,
                    }
                ]
            ),
        ):
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 운동 기록 보여줘",
            )

        self.assertEqual(context.domains, ("exercise",))
        self.assertIn("걷기 | 44분 | 4.2km | 284kcal", context.prompt_text)

    def test_nutrition_question_splits_food_and_water_requests(self) -> None:
        def fake_get(url, **_kwargs):
            if "nutrition_type=eq.food" in url:
                return _response(
                    [
                        {
                            "consumed_at": "2026-08-19T19:20:00+09:00",
                            "meal_type": "dinner",
                            "title": "김치찌개",
                            "calories": 520,
                            "carbohydrate": 60.4,
                            "protein": 22.1,
                            "total_fat": 18.0,
                            "sodium": 1200,
                            "sugar": 6.2,
                        }
                    ]
                )
            return _response(
                [{"consumed_at": "2026-08-19T13:00:00+09:00", "water_amount": 250}]
            )

        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            side_effect=fake_get,
        ) as mocked_get:
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 식단 어때?",
            )

        self.assertEqual(mocked_get.call_count, 2)
        self.assertEqual(context.record_count, 2)
        self.assertIn("저녁 | 김치찌개 | 520kcal", context.prompt_text)
        self.assertIn("나트륨 1,200mg", context.prompt_text)
        self.assertIn("[수분 섭취]", context.prompt_text)
        self.assertIn("250mL", context.prompt_text)

    def test_empty_rows_return_none(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response([]),
        ):
            self.assertIsNone(
                _service().get_relevant_context("token", "user-1", "내 걸음수 어때?")
            )

    def test_missing_values_are_omitted_from_prompt(self) -> None:
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=_response(
                [
                    {
                        "record_date": "2026-08-19",
                        "steps": 4000,
                        "floors_climbed": None,
                        "active_time": None,
                        "active_distance": None,
                        "active_calories": None,
                    }
                ]
            ),
        ):
            context = _service().get_relevant_context(
                "token",
                "user-1",
                "내 걸음수 어때?",
            )

        self.assertEqual(context.prompt_text.splitlines()[-1], "2026-08-19 | 걸음 4,000보")

    def test_rls_denied_response_raises_conversation_error(self) -> None:
        denied = Mock()
        denied.ok = False
        denied.status_code = 401
        denied.headers = {"content-type": "application/json"}
        denied.json.return_value = {
            "message": "permission denied for table lifestyle_activity"
        }
        with patch(
            "app.services.supabase_lifestyle_context.requests.get",
            return_value=denied,
        ):
            with self.assertRaises(SupabaseConversationError) as raised:
                _service().get_relevant_context("token", "user-1", "내 걸음수 어때?")
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
