"""의료 질문의 위험도와 답변 제한 정책을 생성하는 규칙 기반 Guard.

작성자: 김진우
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    """질문의 의료 안전 위험 수준."""

    NORMAL = "normal"
    CAUTION = "caution"
    EMERGENCY = "emergency"


class RestrictedAction(StrEnum):
    """LLM 답변에서 수행하면 안 되는 의료적 결정."""

    DEFINITIVE_DIAGNOSIS = "definitive_diagnosis"
    PERSONALIZED_PRESCRIPTION = "personalized_prescription"
    MEDICATION_DOSE_CHANGE = "medication_dose_change"
    MEDICATION_STOP = "medication_stop"
    MEDICAL_VISIT_DECISION = "medical_visit_decision"
    PERSONALIZED_PROGNOSIS = "personalized_prognosis"


@dataclass(frozen=True)
class GuardResult:
    """응답 경로를 바꾸지 않고 최종 프롬프트에 전달할 안전 정책."""

    triggered: bool
    risk_level: RiskLevel
    restricted_actions: list[str]
    response_policy: str
    emergency: bool
    reason: str | None
    matched_patterns: list[str]


_DISEASE_PATTERN = re.compile(
    r"암|당뇨|고혈압|간질환|신장병|심장병|빈혈|질환|병명|환자|어떤\s*병|"
    r"[가-힣a-z0-9]{2,24}(?:병|암|염|증후군)"
)
_DIAGNOSIS_DECISION_PATTERN = re.compile(
    r"진단해|확정해|결론\s*내려|판단해|단정해|보장해|"
    r"맞는지\s*확실히\s*말해|아닌지\s*결론|"
    r"인지\s*아닌지|이라고\s*진단|인지\s*확정|아니라고\s*결론|"
    r"(?:병|암|염|증후군)\s*(?:이야|인가|맞아|맞나요|인가요)"
)
_MEDICATION_PATTERN = re.compile(r"약|복약|복용|처방|인슐린")
_MEDICATION_ENTITY_PATTERN = re.compile(
    r"[가-힣a-z0-9·+\-]{2,50}(?:카타플라스마|내복액|점안액|캡슐|시럽|주사|연고|크림|과립|정)"
)
_MEDICATION_DECISION_PATTERN = re.compile(
    r"몇\s*알|몇\s*(?:mg|밀리그램)|용량|"
    r"늘(?:려|릴)|줄(?:여|일)|추가로\s*먹|두\s*(?:알|배)(?:로)?\s*먹|"
    r"끊(?:어|을)|중단|바(?:꿔|꿀)|변경|골라\s*줘|선택해\s*줘|"
    r"복용\s*시간(?:을)?\s*(?:바꿔|변경)|"
    r"먹어도\s*(?:돼|되는지|될지)|먹지\s*말아야|"
    r"시작할지\s*결정|처방해|정해\s*줘|결정해\s*줘"
)
_MEDICATION_INTERACTION_LOOKUP_PATTERN = re.compile(
    r"(?:약끼리|약들끼리|내가\s*먹는\s*약).*?(?:같이|함께)\s*먹어도"
)
_EXPLICIT_MEDICATION_CHANGE_PATTERN = re.compile(
    r"몇\s*알|두\s*(?:알|배)(?:로)?|몇\s*(?:mg|밀리그램)|용량|"
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
_PERSONAL_SYMPTOM_PATTERN = re.compile(
    r"(?:나|내가|저|제가|우리\s*(?:아이|부모|엄마|아빠))?.{0,12}"
    r"(?:아파|걸린\s*것\s*같|증상이\s*있|열이\s*나|기침이\s*나|"
    r"어지러|메스꺼|토했|설사해|두통이\s*있).{0,20}"
    r"(?:어떻게|뭘\s*해야|괜찮|도와|알려)"
)
_PERSONAL_PROGNOSIS_PATTERN = re.compile(
    r"(?:나|내가|저|제가|본인).{0,40}"
    r"(?:정확히\s*)?(?:언제|몇\s*(?:일|주|개월)).{0,20}"
    r"(?:완치|회복|낫)|(?:완치|회복).{0,20}(?:날짜|시점|언제)"
)
_PERSONAL_CONTEXT_PATTERN = re.compile(
    r"(?:^|\s)(?:나|난|내가|저|제가|본인|우리\s*(?:아이|부모|엄마|아빠))(?:\s|은|는|이|가)|"
    r"내\s*(?:증상|상태|몸|검사|수치)"
)
_CURRENT_CONTEXT_PATTERN = re.compile(
    r"지금|현재|갑자기|방금|오늘|계속|막\s*생겼|"
    r"(?:증상이|통증이|호흡곤란이|발작이|경련이)\s*(?:있|왔|와|오|생겼|발생했)|"
    r"(?:아프|조이|막히|안\s*쉬어지|못\s*쉬|쓰러졌|의식이\s*없)"
)
_IMMEDIATE_HELP_PATTERN = re.compile(
    r"어떡해|어떻게\s*해야|지금\s*뭘\s*해야|당장|살려|도와\s*줘|"
    r"119|응급실(?:에)?\s*(?:가야|갈까)|바로\s*병원"
)
_INFORMATION_QUERY_PATTERN = re.compile(
    r"(?:증상|원인|예방|예방법|위험\s*요인|치료|대처|정의|뜻|특징|정보)(?:은|는|이|가|을|를)?\s*"
    r"(?:뭐|무엇|어떤|알려|설명|인가|있|하려면)|"
    r"(?:뭐|무엇|어떤)\s*(?:증상|원인|예방법|질환)|"
    r"(?:증상|원인|예방법|위험\s*요인|치료법)(?:은|는|이|가)?\s*[?？]?$"
)
# 명사형 주제 언급과 실제로 발생 중인 표현을 분리한다. 명사만으로 응급 판정하지 않는다.
_EMERGENCY_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("breathing_difficulty", re.compile(r"숨(?:이|을)\s*(?:안\s*쉬|못\s*쉬|막히)|호흡\s*곤란")),
    ("chest_pain", re.compile(r"가슴(?:이|을)?\s*(?:심하게\s*)?(?:아프|조이|짓누르)")),
    ("stroke_sign", re.compile(r"한쪽\s*(?:팔|다리|얼굴).{0,12}(?:마비|힘이\s*없)|말이\s*어눌")),
    ("loss_of_consciousness", re.compile(r"의식(?:이)?\s*(?:없|잃)|깨우(?:지)?\s*않")),
    ("severe_bleeding", re.compile(r"피가\s*(?:계속|멈추지\s*않)|심한\s*출혈")),
    ("seizure", re.compile(r"경련|발작")),
    ("overdose", re.compile(r"과다\s*복용|약을?\s*(?:너무|많이)\s*먹")),
    ("anaphylaxis", re.compile(r"입술|혀|목.{0,8}(?:붓|부었).{0,12}(?:숨|호흡)")),
)

_EXPERIENTIAL_EMERGENCY_PATTERN = re.compile(
    r"숨(?:이)?\s*(?:안\s*쉬어지|못\s*쉬겠|막혀|막히고)|"
    r"가슴(?:이)?\s*(?:심하게\s*)?(?:아파|조여|짓눌려)|"
    r"의식(?:이)?\s*(?:없어|흐려|잃었)|깨우(?:지)?\s*않|"
    r"피가\s*(?:계속|멈추지\s*않)|(?:경련|발작)(?:이)?\s*(?:왔|와|중|하고)|"
    r"약을?\s*(?:너무|많이)\s*먹었"
)


def _normalized(text: str) -> str:
    """공백 변형만 축소하고 원문의 의미 단서는 보존한다."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _policy(
    *,
    risk_level: RiskLevel,
    restrictions: list[RestrictedAction],
    reason: str | None,
    matched_patterns: list[str],
) -> GuardResult:
    """중복을 제거한 안전 정책 결과를 생성한다."""
    restricted_actions = list(dict.fromkeys(action.value for action in restrictions))
    return GuardResult(
        triggered=risk_level is not RiskLevel.NORMAL,
        risk_level=risk_level,
        restricted_actions=restricted_actions,
        response_policy=(
            "emergency_first_grounded_guidance"
            if risk_level is RiskLevel.EMERGENCY
            else "grounded_safe_guidance"
            if risk_level is RiskLevel.CAUTION
            else "standard_grounded"
        ),
        emergency=risk_level is RiskLevel.EMERGENCY,
        reason=reason,
        matched_patterns=matched_patterns,
    )


def check_safety_guard(text: str) -> GuardResult:
    """위험 수준과 금지 행동을 탐지하되 Intent를 변경하지 않는다."""
    normalized = _normalized(text)
    emergency_matches = [
        (name, match.group())
        for name, pattern in _EMERGENCY_TOPIC_PATTERNS
        if (match := pattern.search(normalized)) is not None
    ]
    personal_context = _PERSONAL_CONTEXT_PATTERN.search(normalized)
    current_context = _CURRENT_CONTEXT_PATTERN.search(normalized)
    immediate_help = _IMMEDIATE_HELP_PATTERN.search(normalized)
    information_query = _INFORMATION_QUERY_PATTERN.search(normalized)
    experiential_emergency = _EXPERIENTIAL_EMERGENCY_PATTERN.search(normalized)

    # 위험 단어가 아니라 실제 발생 중인 개인 상황과 즉시 행동 요청의 조합으로 판정한다.
    emergency_context = bool(
        experiential_emergency
        or (personal_context and (current_context or immediate_help))
        or (
            current_context
            and immediate_help
            and not information_query
        )
    )
    if emergency_matches and emergency_context:
        context_matches = [
            match.group()
            for match in (
                personal_context,
                current_context,
                immediate_help,
                information_query,
                experiential_emergency,
            )
            if match is not None
        ]
        return _policy(
            risk_level=RiskLevel.EMERGENCY,
            restrictions=[
                RestrictedAction.DEFINITIVE_DIAGNOSIS,
                RestrictedAction.PERSONALIZED_PRESCRIPTION,
                RestrictedAction.MEDICATION_DOSE_CHANGE,
                RestrictedAction.MEDICATION_STOP,
            ],
            reason="emergency_symptoms",
            matched_patterns=list(
                dict.fromkeys(
                    [value for pair in emergency_matches for value in pair]
                    + context_matches
                )
            ),
        )

    restrictions: list[RestrictedAction] = []
    matches: list[str] = []
    reasons: list[str] = []

    disease_match = _DISEASE_PATTERN.search(normalized)
    diagnosis_match = _DIAGNOSIS_DECISION_PATTERN.search(normalized)
    if diagnosis_match and (
        disease_match
        or personal_context
        or re.search(r"증상이?\s*(?:있|있는|나타)", normalized)
    ):
        restrictions.append(RestrictedAction.DEFINITIVE_DIAGNOSIS)
        if disease_match:
            matches.append(disease_match.group())
        matches.append(diagnosis_match.group())
        reasons.append("definitive_diagnosis")

    prognosis_match = _PERSONAL_PROGNOSIS_PATTERN.search(normalized)
    if prognosis_match:
        restrictions.append(RestrictedAction.PERSONALIZED_PROGNOSIS)
        matches.append(prognosis_match.group())
        reasons.append("personalized_prognosis")

    medication_match = (
        _MEDICATION_PATTERN.search(normalized)
        or _MEDICATION_ENTITY_PATTERN.search(normalized)
    )
    medication_decision_match = _MEDICATION_DECISION_PATTERN.search(normalized)
    interaction_lookup = _MEDICATION_INTERACTION_LOOKUP_PATTERN.search(normalized)
    explicit_change = _EXPLICIT_MEDICATION_CHANGE_PATTERN.search(normalized)
    if (
        medication_match
        and medication_decision_match
        and not (interaction_lookup and not explicit_change)
    ):
        restrictions.append(RestrictedAction.PERSONALIZED_PRESCRIPTION)
        if re.search(
            r"몇\s*알|두\s*(?:알|배)(?:로)?|몇\s*(?:mg|밀리그램)|용량|"
            r"늘(?:려|릴)|줄(?:여|일)",
            normalized,
        ):
            restrictions.append(RestrictedAction.MEDICATION_DOSE_CHANGE)
        if re.search(r"끊(?:어|을)|중단", normalized):
            restrictions.append(RestrictedAction.MEDICATION_STOP)
        matches.extend([medication_match.group(), medication_decision_match.group()])
        reasons.append("medication_decision")

    for pattern_name, pattern in _VISIT_DECISION_PATTERNS:
        visit_match = pattern.search(normalized)
        if visit_match:
            restrictions.append(RestrictedAction.MEDICAL_VISIT_DECISION)
            matches.extend([pattern_name, visit_match.group()])
            reasons.append("medical_visit_decision")
            break

    personal_symptom_match = _PERSONAL_SYMPTOM_PATTERN.search(normalized)
    if personal_symptom_match:
        restrictions.append(RestrictedAction.DEFINITIVE_DIAGNOSIS)
        matches.append(personal_symptom_match.group())
        reasons.append("personal_symptom_guidance")

    if restrictions:
        return _policy(
            risk_level=RiskLevel.CAUTION,
            restrictions=restrictions,
            reason="+".join(dict.fromkeys(reasons)),
            matched_patterns=list(dict.fromkeys(matches)),
        )

    return _policy(
        risk_level=RiskLevel.NORMAL,
        restrictions=[],
        reason=None,
        matched_patterns=[],
    )
