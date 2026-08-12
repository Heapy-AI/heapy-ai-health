"""RDB 표준용어 기반 오타 보정 회귀 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.services.query_resolver import (
    InMemoryMedicalTermRepository,
    MedicalQueryResolver,
    SupabaseMedicalTermRepository,
    build_query_resolver,
)


def _resolver() -> MedicalQueryResolver:
    return MedicalQueryResolver(
        InMemoryMedicalTermRepository(
            [
                {
                    "canonical_key": "DIABETES",
                    "canonical_name": "당뇨병",
                    "term_type": "DISEASE",
                    "aliases": ["당뇨병", "당뇨"],
                },
                {
                    "canonical_key": "HYPERTENSION",
                    "canonical_name": "고혈압",
                    "term_type": "DISEASE",
                    "aliases": ["고혈압"],
                },
                {
                    "canonical_key": "ACETAMINOPHEN",
                    "canonical_name": "아세트아미노펜",
                    "term_type": "MEDICATION",
                    "aliases": ["아세트아미노펜", "타이레놀"],
                },
                {
                    "canonical_key": "IBUPROFEN",
                    "canonical_name": "이부프로펜",
                    "term_type": "MEDICATION",
                    "aliases": ["이부프로펜", "부루펜"],
                },
                {
                    "canonical_key": "HEADACHE",
                    "canonical_name": "두통",
                    "term_type": "SYMPTOM",
                    "aliases": ["두통"],
                },
            ]
        )
    )


class MedicalQueryResolverTest(unittest.TestCase):
    def test_syllable_typo_is_confirmed_before_rewriting(self) -> None:
        result = _resolver().resolve("당뇨뼝 증상")

        self.assertEqual(result.resolved_query, "당뇨뼝 증상")
        self.assertTrue(result.needs_confirmation)
        self.assertIn("당뇨병", result.confirmation_question)
        self.assertEqual(result.terms[0].canonical_key, "DIABETES")
        self.assertEqual(result.terms[0].term_type, "DISEASE")

    def test_normal_hangul_is_not_treated_as_initials(self) -> None:
        resolver = _resolver()

        result = resolver.resolve("하이")
        sentence = resolver.resolve("하이 뭐야")

        self.assertEqual(result.terms, ())
        self.assertEqual(sentence.terms, ())
        self.assertFalse(result.needs_confirmation)
        self.assertFalse(sentence.needs_confirmation)

    def test_low_pressure_is_not_inferred_from_high_pressure(self) -> None:
        result = _resolver().resolve("저혈압")

        self.assertEqual(result.terms, ())
        self.assertEqual(result.resolved_query, "저혈압")

    def test_short_alias_does_not_hide_longer_typo_candidate(self) -> None:
        result = _resolver().resolve("당뇨뼝")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.terms[0].canonical_key, "DIABETES")
        self.assertEqual(result.terms[0].matched_alias, "당뇨병")

    def test_korean_particle_is_not_sent_to_term_lookup(self) -> None:
        result = _resolver().resolve("고혈압이 뭐야")

        self.assertEqual(result.resolved_query, "고혈압이 뭐야")
        self.assertEqual(result.terms[0].source_text, "고혈압")

    def test_brand_alias_resolves_to_medication_canonical_name(self) -> None:
        result = _resolver().resolve("타이레놀 효능")

        self.assertEqual(result.resolved_query, "아세트아미노펜 효능")
        self.assertEqual(result.terms[0].canonical_key, "ACETAMINOPHEN")
        self.assertEqual(result.terms[0].term_type, "MEDICATION")

    def test_keyboard_typo_and_initials_request_confirmation(self) -> None:
        resolver = _resolver()

        typo = resolver.resolve("브르폔 먹고 배아팡")
        initials = resolver.resolve("ㅂㄹㅍ 머야?")

        self.assertEqual(typo.resolved_query, "브르폔 먹고 배아팡")
        self.assertTrue(typo.needs_confirmation)
        self.assertIn("부루펜(이부프로펜)", typo.confirmation_question)
        self.assertNotIn("맞다면", typo.confirmation_question)
        self.assertEqual(typo.terms[0].canonical_key, "IBUPROFEN")
        self.assertEqual(initials.resolved_query, "ㅂㄹㅍ 머야?")
        self.assertTrue(initials.needs_confirmation)
        self.assertIn("부루펜(이부프로펜)", initials.confirmation_question)
        self.assertNotIn("맞다면", initials.confirmation_question)
        self.assertEqual(initials.terms[0].match_kind, "initials")

    def test_syllable_typo_requests_confirmation(self) -> None:
        resolver = _resolver()
        result = resolver.resolve("당냐뱡 어케하지 ㅜㅜ")
        tense_typo = resolver.resolve("당냐뺭 나 어케")
        syllable_typo = resolver.resolve("당나뼝 나 어떻게")

        self.assertEqual(result.resolved_query, "당냐뱡 어케하지 ㅜㅜ")
        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.terms[0].canonical_key, "DIABETES")
        self.assertEqual(tense_typo.resolved_query, "당냐뺭 나 어케")
        self.assertTrue(tense_typo.needs_confirmation)
        self.assertEqual(tense_typo.terms[0].canonical_key, "DIABETES")
        self.assertEqual(syllable_typo.resolved_query, "당나뼝 나 어떻게")
        self.assertTrue(syllable_typo.needs_confirmation)
        self.assertEqual(syllable_typo.terms[0].canonical_key, "DIABETES")

    def test_korean_syllable_typo_uses_the_same_confirmation_flow(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "AST",
                        "canonical_name": "AST",
                        "term_type": "SCREENING",
                        "aliases": ["AST", "간수치"],
                    }
                ]
            )
        )

        result = resolver.resolve("갼슈치 알려줘")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.resolved_query, "갼슈치 알려줘")
        self.assertIn("간수치(AST)", result.confirmation_question)
        self.assertNotIn("맞다면", result.confirmation_question)
        self.assertEqual(result.terms[0].match_kind, "initials")

    def test_initial_substring_is_derived_from_canonical_alias(self) -> None:
        result = _resolver().resolve("ㅎㅇ 뭐야?")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.resolved_query, "ㅎㅇ 뭐야?")
        self.assertEqual(result.terms[0].canonical_key, "HYPERTENSION")
        self.assertEqual(result.terms[0].match_kind, "initials_substring")
        self.assertEqual(result.terms[0].matched_alias, "혈압")
        self.assertIn("혈압(고혈압)", result.confirmation_question)

    def test_initial_only_input_requests_confirmation_before_rewriting(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "AST",
                        "canonical_name": "AST",
                        "term_type": "SCREENING",
                        "aliases": ["AST", "간수치"],
                    }
                ]
            )
        )

        result = resolver.resolve("ㄱㅅㅊ 했어?")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.resolved_query, "ㄱㅅㅊ 했어?")
        self.assertIn("간수치(AST)", result.confirmation_question)
        self.assertNotIn("맞다면", result.confirmation_question)
        self.assertEqual(result.terms[0].match_kind, "initials")

    def test_compound_symptom_keeps_context_and_adds_canonical_hint(self) -> None:
        result = _resolver().resolve("두통증상")

        self.assertIn("두통", result.resolved_query)
        self.assertNotEqual(result.resolved_query, "두통증상")
        self.assertEqual(result.terms[0].canonical_key, "HEADACHE")

    def test_medication_compound_is_not_collapsed_to_disease_alias(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "COMMON_COLD",
                        "canonical_name": "감기",
                        "term_type": "DISEASE",
                        "aliases": ["감기"],
                    }
                ]
            )
        )

        result = resolver.resolve("감기약 뭐였지?")

        self.assertEqual(result.resolved_query, "감기약 뭐였지?")
        self.assertEqual(result.domain_hint, "MEDICATION")
        self.assertEqual(result.terms[0].term_type, "DISEASE")

    def test_unmatched_question_is_unchanged(self) -> None:
        result = _resolver().resolve("오늘 컨디션이 어때")

        self.assertEqual(result.resolved_query, "오늘 컨디션이 어때")
        self.assertEqual(result.terms, ())

    def test_predicate_context_is_not_promoted_to_a_medical_term(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "WEST_NILE",
                        "canonical_name": "웨스트나일열",
                        "term_type": "DISEASE",
                        "aliases": ["웨스트나일열", "나일열"],
                    },
                    {
                        "canonical_key": "AST",
                        "canonical_name": "AST",
                        "term_type": "SCREENING",
                        "aliases": ["AST", "간수치"],
                    },
                ]
            )
        )

        result = resolver.resolve("나 간수치가 너무 낮게 나왔어")

        self.assertFalse(result.needs_confirmation)
        self.assertEqual(result.resolution_status, "RESOLVED")
        self.assertEqual(len(result.terms), 1)
        self.assertEqual(result.terms[0].canonical_name, "AST")
        self.assertNotIn("나일열", result.resolved_query)

    def test_ambiguous_alias_is_not_forced(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "D1",
                        "canonical_name": "감기",
                        "term_type": "DISEASE",
                        "aliases": ["감기"],
                    },
                    {
                        "canonical_key": "S1",
                        "canonical_name": "감기 증상",
                        "term_type": "SYMPTOM",
                        "aliases": ["감기"],
                    },
                ]
            )
        )

        result = resolver.resolve("감기")

        self.assertEqual(result.resolved_query, "감기")
        self.assertEqual(result.terms, ())


class SupabaseMedicalTermRepositoryTest(unittest.TestCase):
    """Supabase 의료용어 일괄 RPC 연결을 검증한다."""

    def test_search_many_uses_single_publishable_key_rpc(self) -> None:
        response = Mock()
        response.json.return_value = [
            {
                "input_query": "AST",
                "canonical_key": "AST",
                "canonical_name": "AST(SGOT)",
                "term_type": "SCREENING",
                "matched_alias": "AST",
                "match_score": 1.0,
                "match_kind": "exact",
                "match_priority": 100,
            }
        ]
        request = Mock(return_value=response)
        repository = SupabaseMedicalTermRepository(
            "https://example.supabase.co",
            "publishable-key",
            request_factory=request,
        )

        result = repository.search_many(["AST", "AST", ""], limit=5)

        self.assertEqual(result["AST"][0].canonical_key, "AST")
        request.assert_called_once()
        self.assertEqual(
            request.call_args.args[0],
            "https://example.supabase.co/rest/v1/rpc/search_medical_terms_batch",
        )
        self.assertEqual(request.call_args.kwargs["headers"]["apikey"], "publishable-key")
        self.assertEqual(request.call_args.kwargs["json"]["p_queries"], ["AST"])

    def test_builder_uses_supabase_when_direct_dsn_is_absent(self) -> None:
        resolver = build_query_resolver(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="publishable-key",
        )

        self.assertIsInstance(resolver.repository, SupabaseMedicalTermRepository)

    def test_exact_lipid_acronym_never_requests_liver_value_confirmation(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "HDL_CHOLESTEROL",
                        "canonical_name": "HDL 콜레스테롤",
                        "term_type": "SCREENING",
                        "aliases": ["HDL"],
                    },
                    {
                        "canonical_key": "LDL_CHOLESTEROL",
                        "canonical_name": "LDL 콜레스테롤",
                        "term_type": "SCREENING",
                        "aliases": ["LDL"],
                    },
                    {
                        "canonical_key": "AST",
                        "canonical_name": "AST",
                        "term_type": "SCREENING",
                        "aliases": ["간수치"],
                    },
                    {
                        "canonical_key": "ALT",
                        "canonical_name": "ALT",
                        "term_type": "SCREENING",
                        "aliases": ["간수치"],
                    },
                    {
                        "canonical_key": "GAMMA_GTP",
                        "canonical_name": "감마지티피",
                        "term_type": "SCREENING",
                        "aliases": ["간수치"],
                    },
                ]
            )
        )

        hdl = resolver.resolve("나의 HDL 수치가 어떤 편이야?")
        ldl = resolver.resolve("나의 LDL 수치가 어떤 편이야?")

        self.assertFalse(hdl.needs_confirmation)
        self.assertFalse(ldl.needs_confirmation)
        self.assertEqual(hdl.terms[0].canonical_key, "HDL_CHOLESTEROL")
        self.assertEqual(ldl.terms[0].canonical_key, "LDL_CHOLESTEROL")
        self.assertNotIn("간수치", hdl.resolved_query)
        self.assertNotIn("간수치", ldl.resolved_query)

    def test_alias_group_exposes_all_screening_canonical_keys(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": code,
                        "canonical_name": code,
                        "term_type": "SCREENING",
                        "aliases": ["간수치"],
                    }
                    for code in ("AST", "ALT", "GAMMA_GTP")
                ]
            )
        )

        result = resolver.resolve("내 간수치 알려줘")

        self.assertFalse(result.needs_confirmation)
        self.assertEqual(result.terms[0].canonical_key, "ALIAS_GROUP:간수치")
        self.assertEqual(
            set(result.terms[0].canonical_keys),
            {"AST", "ALT", "GAMMA_GTP"},
        )

    def test_measurement_context_word_is_not_promoted_to_liver_value(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": code,
                        "canonical_name": code,
                        "term_type": "SCREENING",
                        "aliases": ["간수치"],
                    }
                    for code in ("AST", "ALT", "GAMMA_GTP")
                ]
            )
        )

        result = resolver.resolve("내 수치를 종합해서 설명해줘")

        self.assertFalse(result.needs_confirmation)
        self.assertNotEqual(result.resolution_status, "CONFIRM")
        self.assertEqual(result.terms, ())

    def test_compound_checkup_context_is_not_rewritten_to_unrelated_term(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "ORAL_HEALTH",
                        "canonical_name": "구강검진 결과",
                        "term_type": "SCREENING",
                        "aliases": ["구강검진 결과"],
                    },
                    {
                        "canonical_key": "SCREENING_RESULT_CATEGORY",
                        "canonical_name": "건강검진 판정 구분",
                        "term_type": "SCREENING",
                        "aliases": ["건강검진 판정 구분"],
                    },
                ]
            )
        )

        result = resolver.resolve("내 간 건강 상태를 검진 결과 바탕으로 설명해줘")
        category_result = resolver.resolve(
            "건강검진 결과를 봤을 때 내 간 건강 상태가 어떤 거 같아?"
        )

        self.assertFalse(result.needs_confirmation)
        self.assertEqual(result.terms, ())
        self.assertNotIn("구강검진", result.resolved_query)
        self.assertFalse(category_result.needs_confirmation)
        self.assertEqual(category_result.terms, ())
        self.assertNotIn("판정 구분", category_result.resolved_query)

    def test_abnormal_value_context_does_not_create_false_ambiguity(self) -> None:
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": f"D{index}",
                        "canonical_name": name,
                        "term_type": "DISEASE",
                        "aliases": [name],
                    }
                    for index, name in enumerate(
                        ("척추 형태 이상", "굴절이상", "배뇨 관련 이상"),
                        start=1,
                    )
                ]
            )
        )

        result = resolver.resolve(
            "내 검진 결과에서 서로 연관지어 볼 만한 이상 수치가 있어"
        )

        self.assertFalse(result.needs_confirmation)
        self.assertNotEqual(result.resolution_status, "AMBIGUOUS")
        self.assertEqual(result.terms, ())

    def test_cholesterol_question_resolves_screening_group_without_confirmation(self) -> None:
        cholesterol_terms = [
            {
                "canonical_key": "TOTAL_CHOLESTEROL",
                "canonical_name": "총콜레스테롤",
                "term_type": "SCREENING",
                "aliases": ["총콜레스테롤"],
            },
            {
                "canonical_key": "HDL_CHOLESTEROL",
                "canonical_name": "HDL 콜레스테롤",
                "term_type": "SCREENING",
                "aliases": ["HDL 콜레스테롤"],
            },
            {
                "canonical_key": "LDL_CHOLESTEROL",
                "canonical_name": "LDL 콜레스테롤",
                "term_type": "SCREENING",
                "aliases": ["LDL 콜레스테롤"],
            },
        ]
        liver_terms = [
            {
                "canonical_key": code,
                "canonical_name": code,
                "term_type": "SCREENING",
                "aliases": ["간수치"],
            }
            for code in ("AST", "ALT", "GAMMA_GTP")
        ]
        resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(cholesterol_terms + liver_terms)
        )

        result = resolver.resolve(
            "내 콜레스테롤 수치를 종합해서 심혈관 건강 측면에서 설명해줘"
        )

        self.assertFalse(result.needs_confirmation)
        self.assertEqual(result.resolution_status, "RESOLVED")
        self.assertNotIn("간수치", result.resolved_query)
        self.assertEqual(len(result.terms), 1)
        self.assertTrue(
            {
                "HDL_CHOLESTEROL",
                "LDL_CHOLESTEROL",
            }.issubset(set(result.terms[0].canonical_keys))
        )


if __name__ == "__main__":
    unittest.main()
