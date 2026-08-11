"""의료 Safety Guard 정책 생성 단위 테스트.

작성자: 김진우
"""
import unittest

from app.services.safety_guard import RiskLevel, check_safety_guard


class SafetyGuardTest(unittest.TestCase):
    def test_medical_decisions_create_caution_policy_without_intent_override(self) -> None:
        cases = (
            "검진 수치만으로 내가 암인지 아닌지 결론 내려줘",
            "오늘 약 두 알 먹어도 돼?",
            "내 기록 보고 약을 끊어도 될지 결정해줘",
            "병원 안 가도 되는지 판단해줘",
            "감기 걸린 것 같은데 어떻게 할까?",
        )

        for text in cases:
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertTrue(result.triggered)
                self.assertEqual(result.risk_level, RiskLevel.CAUTION)
                self.assertTrue(result.restricted_actions)
                self.assertEqual(result.response_policy, "grounded_safe_guidance")
                self.assertFalse(result.emergency)

    def test_emergency_symptoms_prioritize_emergency_guidance(self) -> None:
        result = check_safety_guard("숨이 안 쉬어지고 가슴이 심하게 아파요")

        self.assertTrue(result.triggered)
        self.assertEqual(result.risk_level, RiskLevel.EMERGENCY)
        self.assertTrue(result.emergency)
        self.assertEqual(result.response_policy, "emergency_first_grounded_guidance")

    def test_information_lookup_stays_normal(self) -> None:
        cases = (
            "당뇨병 증상이 뭐야?",
            "혈압 정상 범위가 뭐야?",
            "내가 먹는 약끼리 같이 먹어도 되는지 봐줘",
            "호흡곤란의 증상은?",
            "급성호흡곤란증후군을 예방하려면?",
            "일과성 허혈 발작이 있으면 어떤 증상이 나타나나요?",
            "호흡곤란이 발생하면 어떻게 대처해야 하나요?",
        )

        for text in cases:
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertFalse(result.triggered)
                self.assertEqual(result.risk_level, RiskLevel.NORMAL)
                self.assertEqual(result.restricted_actions, [])
                self.assertIsNone(result.reason)

    def test_current_personal_emergency_remains_emergency_for_information_request(
        self,
    ) -> None:
        result = check_safety_guard(
            "나 지금 숨이 안 쉬어지는데 호흡곤란 증상 좀 알려줘"
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.risk_level, RiskLevel.EMERGENCY)
        self.assertTrue(result.emergency)
        self.assertIn("나 ", result.matched_patterns)
        self.assertIn("지금", result.matched_patterns)

    def test_direct_diagnosis_and_dose_questions_are_caution(self) -> None:
        cases = (
            ("이러한 증상이 있는데 파킨슨병이야?", "definitive_diagnosis"),
            (
                "노인성난청 증상이 있는 것 같은데 실제로 노인성난청인지 진단해 주세요.",
                "definitive_diagnosis",
            ),
            ("나 약 두 배로 먹어도 돼?", "medication_dose_change"),
            (
                "제 상태를 확인하지 않고 혜민고카타플라스마를 먹어도 되는지 결정해 주세요.",
                "personalized_prescription",
            ),
            (
                "제가 파라티푸스라면 정확히 언제 완치될지 날짜를 알려주세요.",
                "personalized_prognosis",
            ),
        )

        for text, restriction in cases:
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertTrue(result.triggered)
                self.assertEqual(result.risk_level, RiskLevel.CAUTION)
                self.assertFalse(result.emergency)
                self.assertIn(restriction, result.restricted_actions)


if __name__ == "__main__":
    unittest.main()
