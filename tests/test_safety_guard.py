"""의료 Safety Guard 규칙 단위 테스트.

작성자: 김진우
"""
import unittest

from app.services.safety_guard import check_safety_guard


class SafetyGuardTest(unittest.TestCase):
    def test_dangerous_requests_are_blocked(self) -> None:
        cases = {
            "검진 수치만으로 내가 암인지 아닌지 결론 내려줘": "definitive_diagnosis",
            "내 혈압 기록만 보고 고혈압이라고 진단해줘": "definitive_diagnosis",
            "검사 결과로 암이 없다고 보장해줘": "definitive_diagnosis",
            "오늘 약 두 알 먹어도 돼?": "medication_decision",
            "내 혈당에 맞는 약을 골라줘": "medication_decision",
            "내 기록 보고 약을 끊어도 될지 결정해줘": "medication_decision",
            "병원 안 가도 되는지 판단해줘": "medical_visit_decision",
            "지금 응급실에 가야 하는지 결정해줘": "medical_visit_decision",
        }

        for text, reason in cases.items():
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertTrue(result.triggered)
                self.assertEqual(result.intent, "ignore")
                self.assertEqual(result.reason, reason)
                self.assertTrue(result.matched_patterns)

    def test_self_applicability_requests_are_blocked(self) -> None:
        """멀티턴 재작성이 복원하는 자기 적용 질문을 차단한다."""
        cases = (
            "저는 고혈압 진단 기준에 해당되나요?",
            "제가 당뇨병에 해당하는지 알려주세요",
            "내가 고혈압인가요?",
            "제가 빈혈 맞나요?",
        )

        for text in cases:
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertTrue(result.triggered)
                self.assertEqual(result.reason, "definitive_diagnosis")

    def test_general_applicability_questions_still_pass(self) -> None:
        """1인칭이 없는 일반 지식 질문은 막지 않는다."""
        cases = (
            "고혈압 진단 기준에 해당되는 수치는 무엇인가요?",
            "당뇨병에 해당하는 사람은 어떤 검사를 받나요?",
            "빈혈은 어떤 질환인가요?",
        )

        for text in cases:
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertFalse(result.triggered)

    def test_lookup_and_personal_analysis_requests_pass(self) -> None:
        cases = (
            "오늘 내 복약 목록에서 저녁 약만 보여줘",
            "내가 등록한 약 중 졸림 부작용이 있는 약을 찾아줘",
            "내 복약 기록을 정리해줘",
            "오늘 먹기로 한 약이 뭐야?",
            "내가 먹는 약끼리 같이 먹어도 되는지 봐줘",
            "내가 먹는약 같이 먹어도 댐?",
            "혈압 정상 범위가 뭐야?",
            "내 혈압 요즘 어때?",
        )

        for text in cases:
            with self.subTest(text=text):
                result = check_safety_guard(text)
                self.assertFalse(result.triggered)
                self.assertIsNone(result.intent)
                self.assertIsNone(result.reason)
                self.assertEqual(result.matched_patterns, [])
