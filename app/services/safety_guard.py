"""의료적 결정 요청을 Intent 분류 전에 차단하는 규칙 기반 Guard.

작성자: 김진우
수정: 고수연 (멀티턴 추가)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


IGNORE_INTENT = "ignore"


@dataclass(frozen=True)
class GuardResult:
    """Safety Guard의 작동 여부와 탐지 근거."""

    triggered: bool
    intent: str | None
    reason: str | None
    matched_patterns: list[str]


_DISEASE_PATTERN = re.compile(
    r"암|당뇨|고혈압|간질환|신장병|심장병|빈혈|질환|병명|환자|어떤\s*병"
)
_DIAGNOSIS_DECISION_PATTERN = re.compile(
    r"진단해|확정해|결론\s*내려|판단해|단정해|보장해|"
    r"맞는지\s*확실히\s*말해|아닌지\s*결론|"
    r"인지\s*아닌지|이라고\s*진단|인지\s*확정|아니라고\s*결론"
)
# 멀티턴 후속 질문에서 흔한 자기 적용 요청("그럼 저는 해당되나요?")을 잡는다.
# 재작성기가 직전 대화의 질환명을 복원하면 이 조합이 성립한다. 일반 지식 질문을
# 막지 않도록 1인칭 자기 지칭을 반드시 함께 요구한다.
_SELF_REFERENCE_PATTERN = re.compile(r"제가|저는|저도|저한테|내가|나는|나도|본인이")
_SELF_APPLICABILITY_PATTERN = re.compile(
    r"해당(?:되|하)(?:나요|는지|나|니|냐|ㅂ니까|습니까)|해당됩니까|"
    r"인가요|인건가요|인\s*건가요|맞나요|맞는건가요|맞을까요|아닌가요|"
    r"걸린\s*건가요|걸린\s*걸까요|있는\s*건가요|있는\s*걸까요"
)

_MEDICATION_PATTERN = re.compile(
    r"약|복약|복용|처방|인슐린"
)
_MEDICATION_DECISION_PATTERN = re.compile(
    r"몇\s*알|몇\s*(?:mg|밀리그램)|용량|"
    r"늘(?:려|릴)|줄(?:여|일)|추가로\s*먹|두\s*알\s*먹|"
    r"끊(?:어|을)|중단|바(?:꿔|꿀)|변경|골라\s*줘|선택해\s*줘|"
    r"복용\s*시간(?:을)?\s*(?:바꿔|변경)|"
    r"먹어도\s*(?:돼|되는지|될지)|먹지\s*말아야|"
    r"시작할지\s*결정|처방해|정해\s*줘|결정해\s*줘"
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


def check_safety_guard(text: str) -> GuardResult:
    """진단·약물 결정·내원 판단 요청을 조합 규칙으로 탐지한다."""
    normalized = _normalized(text)

    disease_match = _DISEASE_PATTERN.search(normalized)
    diagnosis_match = _DIAGNOSIS_DECISION_PATTERN.search(normalized)
    if disease_match and diagnosis_match:
        return GuardResult(
            triggered=True,
            intent=IGNORE_INTENT,
            reason="definitive_diagnosis",
            matched_patterns=[disease_match.group(), diagnosis_match.group()],
        )

    self_reference_match = _SELF_REFERENCE_PATTERN.search(normalized)
    applicability_match = _SELF_APPLICABILITY_PATTERN.search(normalized)
    if disease_match and self_reference_match and applicability_match:
        return GuardResult(
            triggered=True,
            intent=IGNORE_INTENT,
            reason="definitive_diagnosis",
            matched_patterns=[
                disease_match.group(),
                self_reference_match.group(),
                applicability_match.group(),
            ],
        )

    medication_match = _MEDICATION_PATTERN.search(normalized)
    medication_decision_match = _MEDICATION_DECISION_PATTERN.search(normalized)
    interaction_lookup = _MEDICATION_INTERACTION_LOOKUP_PATTERN.search(normalized)
    explicit_change = _EXPLICIT_MEDICATION_CHANGE_PATTERN.search(normalized)
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

    for pattern_name, pattern in _VISIT_DECISION_PATTERNS:
        visit_match = pattern.search(normalized)
        if visit_match:
            return GuardResult(
                triggered=True,
                intent=IGNORE_INTENT,
                reason="medical_visit_decision",
                matched_patterns=[pattern_name, visit_match.group()],
            )

    return GuardResult(
        triggered=False,
        intent=None,
        reason=None,
        matched_patterns=[],
    )
