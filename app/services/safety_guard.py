"""의료적 결정 요청을 Intent 분류 전에 차단하는 규칙 기반 Guard.

작성자: 김진우
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.query_resolver import QueryResolution


IGNORE_INTENT = "ignore"


@dataclass(frozen=True)
class GuardResult:
    """Safety Guard의 작동 여부와 탐지 근거."""

    triggered: bool
    intent: str | None
    reason: str | None
    matched_patterns: list[str]


_MEDICAL_CONTEXT_PATTERN = re.compile(
    r"질환|병명|환자|진단|검사|검진|수치|증상|통증|약|복약|복용|처방|병원|진료|치료"
)
_DIAGNOSIS_DECISION_PATTERN = re.compile(
    r"진단해|확정해|결론\s*내려|판단해|단정해|보장해|"
    r"맞는지\s*확실히\s*말해|아닌지\s*결론|"
    r"인지\s*아닌지|이라고\s*진단|인지\s*확정|아니라고\s*결론"
)
_MEDICATION_PATTERN = re.compile(
    r"약|복약|복용|처방"
)
_MEDICATION_DECISION_PATTERN = re.compile(
    r"몇\s*알|몇\s*(?:mg|밀리그램)|용량|"
    r"늘(?:려|릴)|줄(?:여|일)|추가로\s*먹|두\s*알\s*먹|"
    r"끊(?:어|을)|중단|바(?:꿔|꿀)|변경|골라\s*줘|선택해\s*줘|"
    r"추천(?:해)?(?:줘)?|먹을\s*만한|권해\s*줘|"
    r"복용\s*시간(?:을)?\s*(?:바꿔|변경)|"
    r"먹어도\s*(?:돼|되는지|될지)|먹지\s*말아야|"
    r"시작할지\s*결정|처방해|정해\s*줘|결정해\s*줘"
)
_SYMPTOM_PATTERN = re.compile(
    r"아파|아픈|아프|통증|쑤시|결리|불편|열나|구토|토할"
)
_SELF_MEDICATION_PATTERN = re.compile(
    r"뭐\s*(?:먹|복용)|먹을\s*만한|"
    r"(?:어떤|무슨|무엇|어느)\s*(?:약|약물)?\s*(?:을|를)?\s*(?:먹|복용|사용|쓸)|"
    r"(?:먹을|복용할)\s*(?:수\s*있는|만한)?\s*약|"
    r"약\s*(?:이?\s*)?(?:뭐|무엇|어떤|무슨|추천)|"
    r"약.*추천|추천.*약"
)
_MEDICATION_INTERACTION_LOOKUP_PATTERN = re.compile(
    r"(?:약끼리|약들끼리|내가\s*먹는\s*약).*?(?:같이|함께)\s*먹어도"
)
_EXPLICIT_MEDICATION_CHANGE_PATTERN = re.compile(
    r"몇\s*알|두\s*알|몇\s*(?:mg|밀리그램)|용량|"
    r"늘(?:려|릴)|줄(?:여|일)|끊(?:어|을)|중단|바(?:꿔|꿀)|변경|"
    r"골라\s*줘|선택해\s*줘|시작할지\s*결정|처방해"
)
_VISIT_DECISION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("hospital_not_needed", re.compile(r"병원\s*(?:안\s*)?가도\s*(?:돼|되는지)")),
    ("hospital_no_need", re.compile(r"병원에?\s*갈\s*필요\s*(?:없|있는지)")),
    ("emergency_room", re.compile(r"응급실에?\s*(?:바로\s*)?가야\s*(?:해|하는지)")),
    ("emergency_judgment", re.compile(r"응급인지\s*(?:판단|결정)")),
    ("endure_at_home", re.compile(r"집에서\s*버텨도\s*(?:돼|되는지)")),
)


def _normalized(text: str) -> str:
    """공백 변형만 축소하고 원문의 의미 단서는 보존한다."""
    return re.sub(r"\s+", " ", text.strip().lower())


def check_safety_guard(
    text: str,
    *,
    resolution: QueryResolution | None = None,
) -> GuardResult:
    """용어 DB의 분류와 일반적인 요청 행위를 조합해 안전 경로를 선택한다.

    질환명·약품명·검사명 목록은 코드에 두지 않는다. 운영에서는 resolver가
    RDB에서 반환한 ``term_type``을 사용하고, 이 함수는 질문 행위만 판별한다.
    """
    normalized = _normalized(text)

    for pattern_name, pattern in _VISIT_DECISION_PATTERNS:
        visit_match = pattern.search(normalized)
        if visit_match:
            return GuardResult(
                triggered=True,
                intent=IGNORE_INTENT,
                reason="medical_visit_decision",
                matched_patterns=[pattern_name, visit_match.group()],
            )

    diagnosis_match = _DIAGNOSIS_DECISION_PATTERN.search(normalized)
    medical_context_match = _MEDICAL_CONTEXT_PATTERN.search(normalized)
    resolved_medical_term = bool(
        resolution
        and any(term.term_type.strip() for term in resolution.terms)
    )
    if diagnosis_match and (medical_context_match or resolved_medical_term):
        return GuardResult(
            triggered=True,
            intent=IGNORE_INTENT,
            reason="definitive_diagnosis",
            matched_patterns=[
                (medical_context_match or diagnosis_match).group(),
                diagnosis_match.group(),
            ],
        )

    medication_match = _MEDICATION_PATTERN.search(normalized)
    medication_decision_match = _MEDICATION_DECISION_PATTERN.search(normalized)
    interaction_lookup = _MEDICATION_INTERACTION_LOOKUP_PATTERN.search(normalized)
    explicit_change = _EXPLICIT_MEDICATION_CHANGE_PATTERN.search(normalized)
    symptom_match = _SYMPTOM_PATTERN.search(normalized)
    self_medication_match = _SELF_MEDICATION_PATTERN.search(normalized)
    if symptom_match and self_medication_match:
        return GuardResult(
            triggered=True,
            intent=IGNORE_INTENT,
            reason="symptom_medication_advice",
            matched_patterns=[
                symptom_match.group(),
                self_medication_match.group(),
            ],
        )
    if (
        medication_match
        and medication_decision_match
        and not (interaction_lookup and not explicit_change)
    ):
        return GuardResult(
            triggered=True,
            intent=IGNORE_INTENT,
            reason="medication_decision",
            matched_patterns=[
                medication_match.group(),
                medication_decision_match.group(),
            ],
        )

    return GuardResult(
        triggered=False,
        intent=None,
        reason=None,
        matched_patterns=[],
    )
