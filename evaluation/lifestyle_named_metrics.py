"""처음 정한 다섯 지표로 채점한다. 모델을 부르지 않는다.

Accuracy · Groundedness · Hallucination · Answer Rate · 누락 지표.

이 시스템에 맞게 정의를 다시 쓴 곳
--------------------------------
Accuracy       코드가 낸 판정과 답변이 어긋나지 않았는가. 검색 기반이 아니므로
               '정답 문서를 찾았는가'가 아니라 '판정을 뒤집지 않았는가'로 본다.
               어휘로 재는 어림값이라 아래 두 지표보다 미덥지 않다.
Groundedness   답변의 수 가운데 재료에 있는 값의 비율.
Hallucination  지어낸 수 · 재료에 없는 항목명 · 벗어난 것이 없는데 낸 경고.
Answer Rate    필수 자리가 채워진 비율. 구조화 출력이라 대개 100%에 붙는다.
누락 지표       '관리 필요'인데 답변에 없는 항목. 놓치면 안 되는 것만 센다.

읽기 지표를 함께 내는 이유
------------------------
위 다섯은 '틀리지 않았는가'를 잰다. 판정을 코드가 계산해 넘겨주므로 네 판이
대체로 천장에 붙고, 그것만으로는 어느 쪽이 나은지 갈리지 않는다. 그래서 밀도·
길이·행동 특정을 같은 재료로 함께 낸다. 같은 것을 짚으면서 짧은 쪽이 낫다.

재료는 케이스에서 다시 만든다. 합성 구간은 씨앗이 고정돼 있어 언제 돌려도 같다.

실행: python evaluation/lifestyle_named_metrics.py output/lifestyle_prompt_eval/run1.jsonl
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 경고 낱말 목록은 하네스와 한 벌만 둔다.
from evaluation.lifestyle_prompt_eval import ALARM_TERMS  # noqa: E402

CRITICAL = "기준을 크게 벗어남"
# 조언이 손에 잡히는가. 숫자가 없어도 언제·무엇을 하라는 말이면 특정된 것이다.
TARGETED = ("아침", "점심", "저녁", "간식", "주중", "주말", "취침", "기상", "잠자리",
            "하루", "매일", "한 끼", "끼니", "자기 전", "국물", "반찬")
NUMBER = re.compile(r"\d[\d,]*\.?\d*")
SENTENCE = re.compile(r"[^.!?\n]+[.!?\n]?")
# 판정을 뒤집었는지 보는 어휘. 기준을 벗어난 항목을 이렇게 말하면 어긋난 것이다.
POSITIVE = ("좋아", "좋습니다", "잘 유지", "잘 지키", "잘 관리", "충분", "안정적",
            "양호", "적절", "훌륭", "문제없", "괜찮")
# '관리'는 그 자체로 걱정이 아니다. "잘 관리되고 있어요"는 칭찬이다.
# 걱정하는 쪽은 뒤에 붙는 말이 정한다.
NEGATIVE = ("많", "높", "낮", "부족", "벗어", "모자라", "넘", "주의", "아쉬", "줄이",
            "관리가 필요", "관리 필요", "관리해", "관리하", "관리에 신경")
# 사용자에게 쓰지 말라고 한 값들. 낱말 하나만 찾으면 풀어 쓴 표현을 놓친다.
# '기록률'은 안 써도 '기록은 33%만 반영되어'라고 하면 같은 값을 흘린 것이다.
LEAKED = (
    re.compile(r"표준편차|상관계수|변동계수|기록률|coverage|p-value"),
    re.compile(r"기록(?:은|이|된)?\s*(?:약\s*)?\d+(?:\.\d+)?\s*%"),
    re.compile(r"\d+(?:\.\d+)?\s*%(?:의)?\s*(?:날|일)에만"),
    re.compile(r"(?:전반|후반)\s*평균"),
)


# 항목 이름을 낱말 단위로 찾는다. 그냥 찾으면 한 글자 이름('당')이 '당뇨'·'적당히'
# 안에서도 걸린다. 앞뒤가 한글이면 다른 낱말로 보되, 뒤에 붙는 조사는 인정한다.
_PARTICLES = "이|가|은|는|을|를|도|만|의|과|와|에|로|나|이나|이라|부터|까지"


# 같은 것을 가리키는 다른 낱말. 답변은 '깊은수면'을 '깊은 잠'이라고 부른다.
_SAME_MEANING = {"수면": r"(?:수면|잠)"}
# 이름의 낱말 사이에 끼어도 가리키는 대상이 달라지지 않는 말.
# '지방 비중'과 '지방 섭취 비중'은 같은 항목이다.
_FILLER = r"(?:\s|의|섭취|평균|하루)*"


def _one_word(word: str) -> str:
    """이름의 낱말 하나를 찾는 꼴로. 글자 사이 공백과 같은 뜻의 낱말을 열어 둔다."""
    atoms: list[str] = []
    at = 0
    while at < len(word):
        for plain, alternatives in _SAME_MEANING.items():
            if word.startswith(plain, at):
                atoms.append(alternatives)
                at += len(plain)
                break
        else:
            atoms.append(re.escape(word[at]))
            at += 1
    return r"\s*".join(atoms)


def mentions(label: str, text: str) -> bool:
    """답변이 이 항목을 이름으로 부르고 있는가.

    공백은 지우지 않고 살려 둔다. '당 섭취량'에서 공백이 낱말의 끝을 말해 주는데,
    지워 버리면 '당섭취량'이 되어 '당뇨'와 구별할 수 없다. 대신 이름 안쪽에는
    공백이 있어도 되게 한다 — '깊은수면 비중'과 '깊은 수면 비중'은 같은 말이다.

    이름 앞에 한글이 오면 다른 낱말로 본다. '포화지방 섭취 비중'은 '지방 비중'이
    아니다. 이름 뒤에는 한글이 아닌 것이 오거나, 조사가 붙어야 한다.
    """
    name = _FILLER.join(_one_word(word) for word in label.split())
    tail = rf"(?:(?![가-힣])|(?:{_PARTICLES}))"
    return bool(re.search(rf"(?<![가-힣]){name}{tail}", text))


# 조언은 앞으로 할 일이지 지금의 판정이 아니다. Accuracy는 상태를 말하는 자리만 본다.
_ADVICE_FIELDS = ("actions", "recommendations")


def answer_text(answer: dict[str, Any], skip: tuple[str, ...] = ()) -> str:
    parts: list[str] = []
    for key, value in answer.items():
        if key in skip:
            continue
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.extend(str(v) for v in item.values() if isinstance(v, str))
    return "\n".join(parts)


def collect_numbers(node: Any, found: set[float]) -> set[float]:
    if isinstance(node, dict):
        for value in node.values():
            collect_numbers(value, found)
    elif isinstance(node, list):
        for value in node:
            collect_numbers(value, found)
    elif isinstance(node, bool):
        pass
    elif isinstance(node, (int, float)):
        found.add(float(node))
    elif isinstance(node, str):
        for token in NUMBER.findall(node):
            try:
                found.add(float(token.replace(",", "")))
            except ValueError:
                continue
    return found


def derived(allowed: set[float]) -> set[float]:
    """재료의 값에서 사람이 옮겨 적을 만한 꼴을 함께 넓혀 둔다.

    모델이 단위를 바꿔 말하는 것은 지어낸 것이 아니다. 7.99시간을 '7시간 59분'으로,
    0.33을 '33%'로 적는 것이 그렇다. 두 값의 차이(23.45 − 23.26 = 0.19)도 마찬가지다.
    """
    extra: set[float] = set()
    values = [value for value in allowed if value]
    for value in values:
        extra.update({value * 60, value / 60, value * 100, value / 100})
        # 시각·시간을 '몇 시간 몇 분'으로 나눠 적을 때의 분.
        extra.add(round(value % 1 * 60, 2))
    # 같은 항목의 두 구간을 견줘 말한 차이. 재료에 그 수가 직접 있지는 않다.
    for left in values:
        for right in values:
            if left > right:
                extra.add(round(left - right, 2))
    return extra


def grounded(value: float, allowed: set[float]) -> bool:
    for mark in allowed:
        if mark and abs(value - mark) <= max(abs(mark) * 0.06, 0.5):
            return True
        if mark == 0 and value == 0:
            return True
    return value < 10 and value.is_integer()


def build_material() -> dict[str, dict[str, Any]]:
    """케이스마다 모델이 받은 재료를 다시 만든다. 씨앗이 고정돼 결과가 같다."""
    from app.services.lifestyle_report import LifestyleReportService, _prompt_view
    from evaluation.lifestyle_eval_cases import CASES

    return {name: _prompt_view(LifestyleReportService.build_analysis(domain, window))
            for name, domain, window, _ in CASES}


# 한 문장이 두 항목을 반대로 말하는 짜임은 흔하다. 문장이 아니라 절로 봐야 한다.
# "수면 시간은 충분하지만, 깊은 잠의 비중이 계속 부족해요"
CLAUSE_BREAK = re.compile(r"(?<=지만)[,\s]|(?<=으나)[,\s]|(?<=면서)[,\s]|(?<=며)[,\s]"
                          r"|(?<=반면)[,\s]|(?<=다만)[,\s]|(?<=반해)[,\s]"
                          # '충분해도', '길어도' 같은 양보도 앞뒤가 갈린다.
                          r"|(?<=해도)[,\s]|(?<=어도)[,\s]|(?<=아도)[,\s]")
# 항목의 값이 아니라 기록이 얼마나 모였는지를 말하는 자리. 여기의 높낮이는 판정이 아니다.
NOT_A_VALUE = re.compile(r"(?:신뢰도|측정률|기록률|정확도|기록)(?:가|이|은|는|의)?"
                         r"[^,.]{0,12}?(?:높|낮|충분|부족|많|적)")


def clauses(text: str) -> list[str]:
    """문장을 절까지 쪼갠다. 값이 아닌 것의 높낮이는 지운다."""
    parts: list[str] = []
    for line in SENTENCE.findall(text):
        parts.extend(CLAUSE_BREAK.split(line))
    return [NOT_A_VALUE.sub("", part) for part in parts if part]


def stated_as(label: str, state: str, here: set[str]) -> str | None:
    """답변이 이 항목을 어떤 성격으로 말했는가. 말하지 않았으면 None.

    '공복 혈당을 제외한 나머지는 안정적'처럼 그 항목을 빼고 하는 말은 세지 않는다.
    한 항목을 여러 절에서 말했으면 걱정하는 쪽을 따른다. 문제를 짚고 나서 격려로
    마무리하는 것은 흔한 짜임이고, 그때 판정은 앞쪽이다.
    """
    # 이름이 더 긴 항목이 같은 절에 있으면 그쪽 이야기다. '깊은 잠의 비중이 낮다'는
    # '깊은수면'이 아니라 '깊은수면 비중'을 말한 것이다.
    longer = [other for other in here
              if other != label and label.replace(" ", "") in other.replace(" ", "")]
    said = None
    for part in clauses(state):
        if not mentions(label, part):
            continue
        if any(mentions(other, part) for other in longer):
            continue
        if re.search(rf"{re.escape(label)}[을를]?\s*제외", part):
            continue
        if any(word in part for word in NEGATIVE):
            return "부정"
        if any(word in part for word in POSITIVE):
            said = "긍정"
    return said


def service_flagged(view: dict[str, Any], expected: list[dict[str, Any]]) -> bool:
    """서비스가 짚어 준 문제가 하나라도 있는 구간인가.

    벗어난 항목이 없어도 조용한 것은 아니다. 운동은 참고범위를 일부러 두지 않아
    '주 150분에 못 미친다'가 항목 표가 아니라 습관 쪽에 적힌다. 이때 운동이
    모자라다고 말하는 것은 없는 문제를 지어낸 것이 아니라 맞는 말이다.
    """
    if expected:
        return True
    habit = view.get("exercise_habit") or {}
    return "못 미친다" in (habit.get("guideline") or "")


def named_metrics(record: dict[str, Any], view: dict[str, Any],
                  every_label: set[str]) -> dict[str, Any]:
    answer = record["answer"]
    text = answer_text(answer)
    state = answer_text(answer, skip=_ADVICE_FIELDS)
    expected = record["expected_off_range"]
    here = {metric["metric"] for metric in view["metrics"]}
    mentioned = lambda name: mentions(name, text)

    # ① Accuracy — 답변이 성격을 밝힌 항목마다, 서비스 판정과 맞는가.
    #    탭의 모든 항목을 놓고 양쪽으로 센다. 벗어난 것을 괜찮다고 하는 것과
    #    괜찮은 것을 문제라고 하는 것은 둘 다 틀린 것이다.
    off_range = {item["metric"] for item in expected}
    # '지방 비중'이 크게 벗어났으면 "지방 섭취가 많다"도 맞는 말이다. 한 재료의
    # 두 얼굴을 따로 세면, 같은 사실을 말하고도 틀렸다는 판정이 나온다.
    off_range |= {other for other in here for off in set(off_range)
                  if other != off and (other.replace(" ", "") in off.replace(" ", "")
                                       or off.replace(" ", "") in other.replace(" ", ""))}
    # ③ 운동시간은 참고범위를 두지 않은 항목이라, 권고 미달이 습관 쪽에 적힌다.
    habit = view.get("exercise_habit") or {}
    if "못 미친다" in (habit.get("guideline") or ""):
        off_range.add("운동시간")
    judged, flipped, alarmed = 0, [], []
    for metric in view["metrics"]:
        label = metric["metric"]
        said = stated_as(label, state, here)
        if said is None:
            continue  # 말하지 않은 것은 여기서 벌하지 않는다. 누락 지표가 잰다.
        judged += 1
        if label in off_range and said == "긍정":
            flipped.append(label)
        elif label not in off_range and said == "부정":
            alarmed.append(label)

    # ② Groundedness — 답변의 수 가운데 재료에 있는 값. 단위를 바꿔 적은 것도 인정한다.
    allowed = collect_numbers(view, set())
    allowed |= derived(allowed)
    said = [float(token.replace(",", "")) for token in NUMBER.findall(text)]
    invented = [value for value in said if not grounded(value, allowed)]

    # ③ Hallucination — 지어낸 수, 이 탭에 없는 항목명, 없는 문제를 낸 경고.
    outside = sorted({label for label in every_label - here if mentioned(label)})
    false_alarm = 0
    if not service_flagged(view, expected):
        # 걱정하는 말인지 안심시키는 말인지는 낱말 하나로 갈리지 않는다.
        # '과다 섭취하기 쉬운 영양소도 적정 수준'은 괜찮다는 뜻이다.
        false_alarm = sum(
            1 for line in SENTENCE.findall(state)
            if any(term in line for term in ALARM_TERMS)
            and not any(word in line for word in POSITIVE))

    # ④ Answer Rate — 필수 자리가 채워졌는가.
    required = [key for key in ("headline", "current_state", "summary", "overall_analysis")
                if key in answer]
    filled = all(str(answer.get(key) or "").strip() for key in required)
    advice = [line for key in ("actions", "recommendations")
              for line in answer.get(key, []) if isinstance(line, str)]

    # ④-2 통계값을 사용자에게 흘렸는가. Groundedness가 아니라 규칙 위반이다.
    leaked = sum(1 for pattern in LEAKED if pattern.search(text))

    # ⑤ 누락 — '관리 필요'만 필수로 본다.
    critical = [item for item in expected if item["level"] == CRITICAL]
    missed = [item["metric"] for item in critical if not mentioned(item["metric"])]

    # ⑥ 읽기 지표 — 안전한 답변 가운데 어느 쪽이 읽히는가.
    #    같은 것을 짚으면서 짧으면 그쪽이 낫다. 나열은 길이만 늘린다.
    said_items = [item for item in expected if mentioned(item["metric"])]
    targeted = [line for line in advice
                if NUMBER.search(line) or any(word in line for word in TARGETED)]

    return {
        "version": record["version"], "case": record["case"],
        "judged": judged, "flipped": flipped, "alarmed": alarmed,
        "density": len(said_items) / (len(text) / 100) if text else 0.0,
        "length": len(text),
        "targeted": len(targeted) / len(advice) if advice else 0.0,
        "repeat": record["score"]["repeat"],
        "numbers": len(said), "invented": len(invented), "invented_values": invented,
        "outside": outside, "false_alarm": false_alarm,
        "filled": filled, "has_advice": bool(advice), "leaked": leaked,
        "critical_total": len(critical), "critical_missed": len(missed),
        "missed_names": missed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("answers", type=Path)
    args = parser.parse_args()

    material = build_material()
    every_label = {label for view in material.values()
                   for label in (m["metric"] for m in view["metrics"])}

    rows = [named_metrics(json.loads(line), material[json.loads(line)["case"]], every_label)
            for line in args.answers.read_text(encoding="utf-8").splitlines() if line.strip()]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["version"]].append(row)

    print(f"{args.answers.name} — 답변 {len(rows)}건 (모델 호출 없음)\n")
    print(f"   {'판':<5}{'Accuracy':>11}{'Groundedness':>14}{'Hallucination':>15}"
          f"{'Answer Rate':>13}{'누락':>10}{'통계 누출':>11}")
    for name in sorted(groups):
        group = groups[name]
        judged = sum(r["judged"] for r in group)
        wrong = sum(len(r["flipped"]) + len(r["alarmed"]) for r in group)
        said = sum(r["numbers"] for r in group)
        invented = sum(r["invented"] for r in group)
        halluc = invented + sum(len(r["outside"]) for r in group) + sum(
            r["false_alarm"] for r in group)
        need = sum(r["critical_total"] for r in group)
        gone = sum(r["critical_missed"] for r in group)
        print(f"   {name:<5}{(1 - wrong / judged if judged else 1):>10.0%}"
              f"{(1 - invented / said if said else 1):>14.0%}"
              f"{halluc / len(group):>13.2f}건"
              f"{fmean(r['filled'] and r['has_advice'] for r in group):>13.0%}"
              f"{f'{gone}/{need}':>10}"
              f"{fmean(r['leaked'] for r in group):>11.2f}")

    print("\n   Accuracy       성격을 밝힌 항목 중 서비스 판정과 맞은 비율. 어휘로 잰 어림값")
    print("   Groundedness   답변의 수 가운데 재료에 있는 값의 비율")
    print("   Hallucination  한 답변당 지어낸 수 + 없는 항목명 + 헛경고")
    print("   Answer Rate    필수 자리와 조언이 모두 채워진 비율")
    print("   누락           '관리 필요'인데 답변에 없는 항목 수 / 전체")
    print("   통계 누출      기록률·표준편차 같은 값을 사용자에게 그대로 말한 답변당 건수")

    print(f"\n   {'판':<5}{'밀도':>9}{'길이':>9}{'행동 특정':>11}{'되풀이':>10}")
    for name in sorted(groups):
        group = groups[name]
        print(f"   {name:<5}{fmean(r['density'] for r in group):>9.2f}"
              f"{fmean(r['length'] for r in group):>9.0f}"
              f"{fmean(r['targeted'] for r in group):>11.0%}"
              f"{fmean(r['repeat'] for r in group):>10.0%}")
    print("\n   밀도       짚은 이상 항목 수 ÷ 100자. 덜 쓰고 더 담았는가")
    print("   길이       사용자가 읽는 글자 수")
    print("   행동 특정  조언에 숫자·시점·대상이 잡힌 비율")
    print("   되풀이     머리글이 본문과 겹치는 정도. 참고값이다")

    print("\n무엇이 걸렸나\n")
    for name in sorted(groups):
        group = groups[name]
        notes = []
        flipped = [f"{r['case'][:9]}·{m}" for r in group for m in r["flipped"]]
        outside = [f"{r['case'][:9]}·{m}" for r in group for m in r["outside"]]
        missed = [f"{r['case'][:9]}·{m}" for r in group for m in r["missed_names"]]
        values = sorted({v for r in group for v in r["invented_values"]})
        alarmed = [f"{r['case'][:9]}·{m}" for r in group for m in r["alarmed"]]
        if flipped:
            notes.append(f"판정 뒤집음 {', '.join(flipped)}")
        if alarmed:
            notes.append(f"정상인데 문제라 함 {', '.join(alarmed)}")
        if outside:
            notes.append(f"이 탭에 없는 항목 {', '.join(outside)}")
        if values:
            notes.append(f"지어낸 수 {', '.join(f'{v:g}' for v in values[:6])}")
        if missed:
            notes.append(f"놓친 관리필요 {', '.join(missed)}")
        print(f"   {name}  {' / '.join(notes) or '없음'}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
