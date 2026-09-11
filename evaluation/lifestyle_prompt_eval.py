"""생활건강 프롬프트 v1~v4를 같은 재료로 돌려 견준다.

무엇을 재는가
--------------
이 시스템은 판정을 코드가 하므로 **정답지가 결정적으로 존재한다.** 서비스가 만든
analysis_input이 곧 정답이다. 그래서 사람 채점이나 심판 모델 없이도 대부분 자동으로
잴 수 있다. 아래 여섯 지표가 모두 그렇게 계산된다.

무엇을 재는 것이 아닌가
--------------------
**지금 파이프라인에서 각 프롬프트가 얼마나 잘 맞는지**를 잰다. "그때 그 버전이
얼마나 좋았나"가 아니다. 재료는 v4에 맞춰 손질돼 있어서(원시 통계를 걷어내고,
당연한 짝을 거르고, 비중 지표를 더했다) 옛 판에는 불리하다. 특히 v1은 항목마다
previous·change 같은 수치를 요구하는데 지금 재료에 그 값이 없어, 지어내지 않고는
제 출력 계약을 채울 수 없다. 그 점이 수치 충실도 점수에 그대로 드러난다.

출력 계약은 판마다 달라서 각자 제 계약으로 받는다. 지표는 계약과 무관하게 답변
텍스트 전체를 이어 붙여 계산한다.

실행: python evaluation/lifestyle_prompt_eval.py [--runs 1]

작성자: 고수연
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import requests
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.core.config import MODEL  # noqa: E402
from app.schemas.lifestyle_report import (  # noqa: E402
    LifestyleReportContent,
    LifestyleReportContentV1,
)
from app.services.lifestyle_report import (  # noqa: E402
    DOMAIN_LABELS,
    LifestyleReportService,
    _prompt_view,
)
from app.services.prompts import (  # noqa: E402
    lifestyle_report_v1,
    lifestyle_report_v2,
    lifestyle_report_v3,
    lifestyle_report_v4,
)
from app.services.supabase_personal_data import SupabasePersonalDataService  # noqa: E402
from evaluation.lifestyle_eval_cases import CASES  # noqa: E402


class LifestyleReportContentV2(BaseModel):
    """v2.0·v3.0의 출력 계약. 요약 자리(key_points)가 있던 판이다."""

    headline: str
    current_state: str
    key_points: list[str] = Field(default_factory=list, max_length=3)
    actions: list[str] = Field(default_factory=list, max_length=3)


VERSIONS = (
    ("v1", lifestyle_report_v1, LifestyleReportContentV1),
    ("v2", lifestyle_report_v2, LifestyleReportContentV2),
    ("v3", lifestyle_report_v3, LifestyleReportContentV2),
    ("v4", lifestyle_report_v4, LifestyleReportContent),
)

# 벗어난 정도에 따라 놓쳤을 때의 대가가 다르다. 관리 필요는 반드시 짚어야 한다.
LEVEL_WEIGHT = {"기준을 크게 벗어남": 2, "기준을 조금 벗어남": 1}

# 프롬프트가 사용자에게 쓰지 말라고 명시한 것들. 규칙이 뚜렷해 자동으로 셀 수 있다.
BANNED_TERMS = ("표준편차", "상관계수", "변동계수", "기록률", "coverage", "p-value")
CAUSAL_TERMS = ("때문에", "때문입니다", "탓에", "원인은", "때문이에요")
# 조언이 손에 잡히는지. 숫자·시각·횟수가 하나라도 있으면 구체적인 것으로 본다.
CONCRETE = re.compile(r"\d")
# 벗어난 항목이 없는 구간에서 이런 말이 나오면 없는 문제를 지어낸 것이다.
ALARM_TERMS = ("관리가 필요", "관리 필요", "벗어나", "부족한", "부족합니다", "모자라",
               "과다", "지나치", "높은 편", "낮은 편", "주의가 필요", "개선이 필요")
NUMBER = re.compile(r"\d[\d,]*\.?\d*")


def collect_numbers(node: Any, found: set[float]) -> set[float]:
    """재료 안에 있는 모든 수를 모은다. 답변의 수를 이것과 견준다."""
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


def grounded(value: float, allowed: set[float]) -> bool:
    """답변의 수가 재료에 있는 값인가. 어림수로 옮겨 적는 것은 허용한다."""
    for mark in allowed:
        if mark == 0:
            if value == 0:
                return True
            continue
        if abs(value - mark) <= max(abs(mark) * 0.06, 0.5):
            return True
    # 한 자리 수는 문장에 흔히 섞인다(두 가지·세 번). 지어낸 수로 보지 않는다.
    return value < 10 and value.is_integer()


def answer_text(report: BaseModel) -> str:
    """계약이 달라도 사용자가 읽는 글은 다 이어 붙여 같은 잣대로 본다."""
    parts: list[str] = []
    for value in report.model_dump().values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.extend(str(v) for v in item.values() if isinstance(v, str))
    return "\n".join(parts)


def advice_lines(report: BaseModel) -> list[str]:
    """조언에 해당하는 줄. 판마다 이름이 다르다."""
    data = report.model_dump()
    return [line for key in ("actions", "recommendations")
            for line in data.get(key, []) if isinstance(line, str)]


def score(view: dict[str, Any], report: BaseModel, other_labels: set[str]) -> dict[str, float]:
    """정답지(view)와 답변을 견줘 여섯 지표를 낸다."""
    text = answer_text(report)
    metrics = view.get("metrics", [])

    # ① 이상 항목 커버리지. 기준을 벗어난 항목을 빠짐없이 짚었는가.
    need, hit = 0, 0
    missed = []
    for metric in metrics:
        level = (metric.get("recent") or metric.get("full") or {}).get("level", "")
        weight = LEVEL_WEIGHT.get(level, 0)
        if not weight:
            continue
        need += weight
        name = metric["metric"]
        # '수축기 혈압'처럼 합쳐 부르는 이름도 인정한다.
        if name in text or name.replace(" ", "") in text.replace(" ", ""):
            hit += weight
        else:
            missed.append(name)

    # ② 수치 충실도. 답변에 나온 수가 재료에 있는 값인가.
    allowed = collect_numbers(view, set())
    said = [float(token.replace(",", "")) for token in NUMBER.findall(text)]
    invented = [value for value in said if not grounded(value, allowed)]

    # ③ 금지 규칙 위반.
    violations = sum(term in text for term in BANNED_TERMS)
    violations += sum(term in text for term in CAUSAL_TERMS)
    violations += sum(1 for label in other_labels if label in text)
    dates = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}월 \d{1,2}일", text)
    violations += 1 if len(dates) >= 2 else 0

    # ④ 조언 구체성. 숫자로 손에 잡히게 썼는가.
    advice = advice_lines(report)
    concrete = sum(1 for line in advice if CONCRETE.search(line))

    # ⑤ 거짓양성. 벗어난 항목이 없는데 문제가 있다고 말하는가.
    # 이 구간에서는 커버리지가 1.0으로 고정돼 잴 것이 없으므로 이쪽으로 본다.
    alarms = sum(term in text for term in ALARM_TERMS) if need == 0 else 0

    # ⑥ 되풀이율. 머리글과 본문이 같은 말인가.
    data = report.model_dump()
    head = set(re.findall(r"[가-힣]{2,}", str(data.get("headline", ""))))
    body = set(re.findall(r"[가-힣]{2,}", str(data.get("current_state") or data.get("summary") or "")))
    repeat = len(head & body) / len(head) if head else 0.0

    return {
        "coverage": hit / need if need else 1.0,
        "missed": missed,
        "numbers": len(said),
        "invented": len(invented),
        "invented_values": invented,
        "fidelity": 1 - len(invented) / len(said) if said else 1.0,
        "violations": violations,
        "alarms": alarms,
        "scored_coverage": need > 0,
        "advice": len(advice),
        "actionability": concrete / len(advice) if advice else 0.0,
        "repeat": repeat,
        "length": len(text),
    }


def build_prompt(module: Any, domain: str, analysis: dict[str, Any]) -> str:
    """서비스와 같은 방식으로 짜되 프롬프트 판만 갈아 끼운다.

    판마다 요구하는 자리가 다르다. v1은 window_days를, v3·v4는 latest_date를 쓴다.
    쓰지 않는 자리를 넘겨도 format이 무시하므로 다 채워 넘긴다.
    """
    return module.REPORT_PROMPT.format(
        common_rules=module.COMMON_RULES,
        domain_guide=module.DOMAIN_GUIDES.get(domain, ""),
        domain_label=DOMAIN_LABELS.get(domain, domain),
        latest_date=analysis["latest_date"] or "기록 없음",
        window_days=analysis["windows"]["full"],
        analysis_data=json.dumps(_prompt_view(analysis), ensure_ascii=False, indent=2),
    )


def load_windows() -> dict[str, dict[str, Any]]:
    """기록이 가장 많은 사용자 한 명의 실제 구간을 탭마다 만든다."""
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    head = {"apikey": key, "Authorization": f"Bearer {key}"}

    def get(path: str) -> list[dict[str, Any]]:
        return requests.get(f"{url}/rest/v1/{path}", headers=head, timeout=30).json()

    bio = get("lifestyle_bio?select=*&order=measured_at.desc&limit=3000")
    owner = Counter(row["user_id"] for row in bio).most_common(1)[0][0]
    mine = lambda rows: [row for row in rows if row.get("user_id") == owner]

    food = get("lifestyle_nutrition?nutrition_type=eq.food&select=user_id,consumed_at,meal_type,"
               "title,calories,carbohydrate,protein,total_fat,sodium,sugar,saturated_fat,"
               "dietary_fiber,potassium,calcium&order=consumed_at.desc&limit=3000")
    water = get("lifestyle_water_intake?select=user_id,consumed_at,water_amount:amount_ml"
                "&order=consumed_at.desc&limit=3000")
    activity = get("lifestyle_activity?select=user_id,record_date,steps,floors_climbed:floors,"
                   "active_time:active_time_minutes,active_distance_km:distance_m,"
                   "active_calories:active_calories_kcal&order=record_date.desc&limit=3000")
    exercise = get("lifestyle_exercise?select=user_id,record_date:start_at,exercise_type,"
                   "duration_sec:duration_seconds,distance_m,calories:calories_kcal"
                   "&order=start_at.desc&limit=3000")
    sleep = get("lifestyle_sleep?select=user_id,measured_at:start_at,start_at,end_at,"
                "total_sleep_minutes,awake_minutes,deep_sleep_minutes,light_sleep_minutes,"
                "rem_sleep_minutes,sleep_score&order=start_at.desc&limit=3000")

    normalize = SupabasePersonalDataService._normalize_domain
    return {
        "bio": {"bio": normalize("bio", {"rows": mine(bio)})},
        "activity": {"activity": {"rows": mine(activity)}, "exercise": {"rows": mine(exercise)}},
        "nutrition": {"food": {"rows": mine(food)}, "water": {"rows": mine(water)}},
        "sleep": {"sleep": normalize("sleep", {"rows": mine(sleep)})},
    }


async def run_once(module: Any, schema: type[BaseModel], domain: str,
                   analysis: dict[str, Any]) -> BaseModel:
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0).with_structured_output(schema)
    return await llm.ainvoke(build_prompt(module, domain, analysis))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1,
                        help="구간·판마다 몇 번 돌릴지. 0이면 정답지만 보고 끝낸다")
    parser.add_argument("--only", choices=("cases", "real"), help="한쪽만 돌린다")
    parser.add_argument("--save", nargs="?", const="", default=None, metavar="경로",
                        help="답변 원문과 채점을 jsonl로 남긴다. 경로를 비우면 output/에 쓴다")
    args = parser.parse_args()

    # 합성 구간은 어디서 무너지는지 찾는 쪽, 실제 기록은 현실에서도 그런지 보는 쪽이다.
    windows: dict[str, tuple[str, dict[str, Any]]] = {}
    if args.only != "real":
        windows.update({name: (domain, window) for name, domain, window, _ in CASES})
    if args.only != "cases":
        windows.update({f"실제-{DOMAIN_LABELS[domain]}": (domain, window)
                        for domain, window in load_windows().items()})
    analyses = {name: LifestyleReportService.build_analysis(domain, window)
                for name, (domain, window) in windows.items()}
    views = {name: _prompt_view(analysis) for name, analysis in analyses.items()}
    labels = {name: {m["metric"] for m in view["metrics"]} for name, view in views.items()}

    print("정답지 — 기준을 벗어난 항목\n")
    for name, view in views.items():
        off = [m["metric"] for m in view["metrics"]
               if (m.get("recent") or m.get("full") or {}).get("level") in LEVEL_WEIGHT]
        print(f"   {name:<16}{len(off)}개  {' · '.join(off) or '없음 (거짓양성으로 잰다)'}")

    if not args.runs:
        # 정답지만 보고 끝낸다. 케이스가 타당한지 확인하고 나서 토큰을 쓰라는 뜻이다.
        print(f"\n예행 모드 — 모델을 부르지 않았다. --runs 1로 돌리면 "
              f"{len(VERSIONS) * len(analyses)}회 부른다.")
        return

    scores: dict[str, list[dict[str, Any]]] = defaultdict(list)
    saved: list[dict[str, Any]] = []
    calls = len(VERSIONS) * len(analyses) * args.runs
    print(f"\n모델 호출 {calls}회 — {len(analyses)}구간 × {len(VERSIONS)}판 × {args.runs}회\n")
    for name, module, schema in VERSIONS:
        for case, analysis in analyses.items():
            domain = windows[case][0]
            others = {label for tab, names in labels.items() if tab != case for label in names}
            for index in range(args.runs):
                report = asyncio.run(run_once(module, schema, domain, analysis))
                result = score(views[case], report, others - labels[case])
                result["case"] = case
                scores[name].append(result)
                if args.save is not None:
                    saved.append({
                        "version": name, "case": case, "domain": domain, "run": index,
                        # 정답지를 함께 남긴다. 나중에 답변만 보고는 채점을 다시 못 한다.
                        "expected_off_range": [
                            {"metric": m["metric"],
                             "level": (m.get("recent") or m.get("full") or {}).get("level")}
                            for m in views[case]["metrics"]
                            if (m.get("recent") or m.get("full") or {}).get("level") in LEVEL_WEIGHT
                        ],
                        "answer": report.model_dump(),
                        "score": {k: v for k, v in result.items() if k != "case"},
                    })
        done = [r for r in scores[name] if r["scored_coverage"]]
        print(f"{name} 마침 — 커버리지 {fmean(r['coverage'] for r in done):.0%}")

    print("\n" + "=" * 78)
    print(f"\n   {'판':<5}{'커버리지':>9}{'수치 충실도':>12}{'거짓양성':>10}"
          f"{'규칙 위반':>10}{'조언 구체성':>12}{'되풀이':>9}{'길이':>8}")
    for name, _, _ in VERSIONS:
        rows = scores[name]
        covered = [r for r in rows if r["scored_coverage"]] or rows
        quiet = [r for r in rows if not r["scored_coverage"]]
        print(f"   {name:<5}{fmean(r['coverage'] for r in covered):>8.0%}"
              f"{fmean(r['fidelity'] for r in rows):>12.0%}"
              f"{(fmean(r['alarms'] for r in quiet) if quiet else 0):>10.1f}"
              f"{fmean(r['violations'] for r in rows):>10.1f}"
              f"{fmean(r['actionability'] for r in rows):>12.0%}"
              f"{fmean(r['repeat'] for r in rows):>9.0%}"
              f"{fmean(r['length'] for r in rows):>8.0f}")
    print("\n   커버리지는 벗어난 항목이 있는 구간만, 거짓양성은 없는 구간만 셈한다.")

    print("\n놓친 항목 (커버리지가 깎인 이유)\n")
    for name, _, _ in VERSIONS:
        missed = Counter(item for row in scores[name] for item in row["missed"])
        print(f"   {name}  {', '.join(f'{k}×{v}' for k, v in missed.most_common(6)) or '없음'}")

    print("\n지어낸 수 (재료에 없는 값)\n")
    for name, _, _ in VERSIONS:
        rows = scores[name]
        values = sorted({value for row in rows for value in row["invented_values"]})
        print(f"   {name}  답변의 수 {sum(r['numbers'] for r in rows):>3}개 중 "
              f"{sum(r['invented'] for r in rows):>2}개"
              + (f"   {', '.join(f'{v:g}' for v in values[:8])}" if values else ""))

    if args.save is not None:
        target = Path(args.save) if args.save else (
            ROOT / "output" / "lifestyle_prompt_eval"
            / f"answers-{datetime.now():%Y%m%d-%H%M}.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as file:
            for record in saved:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\n답변 {len(saved)}건을 남겼다 → {target}")
        print("   자동으로 못 재는 것(길이와 횟수를 가려 말했는지 등)은 이 파일을 읽고 본다.")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
