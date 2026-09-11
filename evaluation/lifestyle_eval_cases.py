"""프롬프트를 견주기 위한 합성 구간.

왜 합성인가
-----------
정답지를 사람이 라벨링하지 않는다. 서비스 코드가 참고범위와 견줘 계산한다. 그래서
입력이 실제 기록이냐 만들어 낸 기록이냐가 정답지의 신뢰도를 흔들지 않는다. 대신
**의도한 상황을 골라 만들 수 있다.** 실제 사용자 다섯 명의 기록으로는 '전부 정상인
달'이나 '혈압이 반년에 걸쳐 오르는 구간'을 구할 수 없다.

값이 날마다 흔들려야 한다
-----------------------
처음 만든 구간은 날마다 값이 똑같았다(나트륨 3,600이 30일 내내). 그러면 서비스가
내는 여섯 신호 가운데 **둘만 살아 있다.**

    수준·빈도    살아 있음
    방향        전부 '큰 변화 없음'  — 값이 안 움직이니까
    안정성      전부 '안정적'       — 표준편차가 0이니까
    이상 지점    나오지 않음

그러면 "조금씩 오르는 흐름"이나 "날마다 편차가 큼"을 프롬프트가 제대로 옮기는지 잴
수가 없다. 이 프로젝트에서 실제로 문제가 됐던 것이 그쪽이다 — 운동량이 그대로인데
"줄어들고 있어요"라고 한 것, 혈압이 "계속 오르는 흐름"인 것.

그래서 구간마다 흔들림 폭과 추세를 정해 넣는다. 흔들림은 씨앗을 고정한 난수라
언제 돌려도 같은 값이 나온다.

무엇을 증명하지 못하나
--------------------
실제 사용자에서의 성능. 합성 구간은 현실보다 규칙적이다. 그래서 실제 기록과
**함께** 재야 한다. 합성은 어디서 무너지는지 찾는 쪽, 실데이터는 현실에서도 그런지
보는 쪽이다.

실행 (모델 호출 0회)
    python evaluation/lifestyle_eval_cases.py            정답지를 화면에 찍는다
    python evaluation/lifestyle_eval_cases.py --export   기록과 정답지를 파일로 뜬다

작성자: 고수연
"""

from __future__ import annotations

import argparse
import io
import json
import math
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

END = date(2026, 9, 1)


def days_back(count: int, step: int = 1) -> list[str]:
    """최신 기록일에서 거슬러 올라간 날짜들. 오래된 날이 앞에 온다."""
    return [str(END - timedelta(days=back)) for back in range(0, count * step, step)][::-1]


def wave(base: float, count: int, *, seed: int, spread: float = 0.08,
         drift: float = 0.0, spike: float = 0.0, smooth: bool = False) -> list[float]:
    """날마다 흔들리는 값.

    spread  하루하루의 흔들림 폭. 안정성 판정(변동계수)이 여기서 나온다.
    drift   구간 처음과 끝의 차이 비율. 방향 판정이 여기서 나온다.
    spike   가운데 하루를 이 배수만큼 튀게 한다. 이상 지점 판정이 여기서 나온다.
    smooth  난수 대신 물결로 흔든다. 난수는 서른 번쯤 뽑으면 표본 표준편차가
            작게 잡히는 날이 있어 '평소와 크게 다른 날'로 걸린다. 조용해야 하는
            구간에서는 그 한 날이 거짓양성 지표를 흐리므로 물결을 쓴다.
    """
    rng = random.Random(seed)
    values = []
    for index in range(count):
        ramp = 1 + drift * (index / max(count - 1, 1) - 0.5)
        if smooth:
            shake = math.sin(index * 0.7 + seed) * spread
        else:
            shake = rng.uniform(-spread, spread)
        values.append(round(base * ramp * (1 + shake), 2))
    if spike:
        values[count // 2] = round(base * spike, 2)
    return values


def _nutrition(count: int, *, seed: int, spread: float = 0.08, water: float = 1800,
               smooth: bool = False, **grams: float) -> dict[str, Any]:
    """식사 기록. 영양소마다 따로 흔들려야 비중도 날마다 달라진다."""
    marks = days_back(count)
    series = {name: wave(value, count, seed=seed + offset, spread=spread, smooth=smooth)
              for offset, (name, value) in enumerate(grams.items())}
    drinks = wave(water, count, seed=seed + 90, spread=spread, smooth=smooth)
    return {
        "food": {"rows": [
            {"consumed_at": f"{day}T12:30:00", "meal_type": "lunch",
             **{name: series[name][index] for name in series}}
            for index, day in enumerate(marks)]},
        "water": {"rows": [
            {"consumed_at": f"{day}T15:00:00", "water_amount": drinks[index]}
            for index, day in enumerate(marks)]},
    }


def _bio(count: int, *, seed: int, systolic: float, diastolic: float, glucose: float,
         bmi: float, heart_rate: float, step: int = 1, spread: float = 0.04,
         drift: float = 0.0) -> dict[str, Any]:
    """생체 기록. 혈압에 추세를 주면 혈당·BMI는 그보다 완만하게 따라 움직인다."""
    marks = days_back(count, step)
    plan = (("systolic", systolic, drift), ("glucose", glucose, drift * 0.4),
            ("bmi", bmi, drift * 0.2), ("heart_rate", heart_rate, 0.0))
    series = {name: wave(base, count, seed=seed + offset, spread=spread, drift=slope)
              for offset, (name, base, slope) in enumerate(plan)}
    lower = wave(diastolic, count, seed=seed + 50, spread=spread, drift=drift)
    rows: list[dict[str, Any]] = []
    for index, day in enumerate(marks):
        upper = series["systolic"][index]
        rows += [
            {"measured_at": f"{day}T07:00:00", "bio_type": "blood_pressure", "value": upper,
             "detail_data": {"systolic": upper, "diastolic": lower[index]}},
            {"measured_at": f"{day}T07:10:00", "bio_type": "blood_glucose",
             "value": series["glucose"][index], "detail_data": {"fasting": True}},
            {"measured_at": f"{day}T07:20:00", "bio_type": "bmi",
             "value": series["bmi"][index], "detail_data": {}},
            {"measured_at": f"{day}T07:30:00", "bio_type": "heart_rate",
             "value": series["heart_rate"][index], "detail_data": {}},
            {"measured_at": f"{day}T07:40:00", "bio_type": "weight",
             "value": round(series["bmi"][index] * 3.06, 1), "detail_data": {}},
        ]
    return {"bio": {"rows": rows}}


def _sleep(count: int, *, seed: int, score: float, deep: float, light: float,
           rem: float, awake: float, spread: float = 0.10) -> dict[str, Any]:
    """수면 기록. 총 수면시간은 단계의 합으로 낸다. 따로 흔들면 둘이 어긋난다."""
    marks = days_back(count)
    stages = ("deep", "light", "rem", "awake")
    parts = {name: wave(value, count, seed=seed + offset, spread=spread)
             for offset, (name, value) in enumerate(zip(stages, (deep, light, rem, awake)))}
    points = wave(score, count, seed=seed + 9, spread=0.06)
    return {"sleep": {"rows": [
        {"measured_at": f"{day}T23:30:00", "bio_type": "sleep", "unit": "hour",
         "value": round(sum(parts[name][index] for name in stages) / 60, 2),
         "detail_data": {"sleep_score": round(points[index]),
                         "deep_sleep_minutes": parts["deep"][index],
                         "light_sleep_minutes": parts["light"][index],
                         "rem_sleep_minutes": parts["rem"][index],
                         "awake_minutes": parts["awake"][index],
                         "start_at": f"{day}T14:30:00+00:00", "end_at": f"{day}T22:30:00+00:00"}}
        for index, day in enumerate(marks)
    ]}}


def _activity(count: int, *, seed: int, steps: float, calories: float,
              workout_every: int, minutes: float, spread: float = 0.12,
              drift: float = 0.0, spike: float = 0.0) -> dict[str, Any]:
    marks = days_back(count)
    walked = wave(steps, count, seed=seed, spread=spread, drift=drift, spike=spike)
    burned = wave(calories, count, seed=seed + 1, spread=spread, drift=drift)
    return {
        "activity": {"rows": [{"record_date": day, "steps": round(walked[index]),
                               "active_calories": burned[index]}
                              for index, day in enumerate(marks)]},
        "exercise": {"rows": [
            {"record_date": f"{day}T18:00:00", "exercise_type": "walking",
             "duration_sec": minutes * 60, "distance_m": 4000, "calories": minutes * 6}
            for index, day in enumerate(marks) if index % workout_every == 0
        ]},
    }


# 수치는 참고범위와 판정 문턱을 겨냥해 고른 값이다. 실제로 어떤 판정이 나오는지는
# 이 파일을 직접 실행해 확인한다. 코드가 계산한 결과가 곧 정답지다.
CASES: tuple[tuple[str, str, dict[str, Any], str], ...] = (
    ("영양-전부정상", "nutrition",
     # 흔들려도 어느 날 하나 경계를 넘지 않도록 여유를 두고 잡은 값이다.
     # 튀는 날도 없어야 해서 물결로 흔든다.
     _nutrition(30, seed=11, smooth=True,
                calories=2000, carbohydrate=280, protein=80, total_fat=58,
                saturated_fat=12, sodium=1500, sugar=30, dietary_fiber=25,
                potassium=4200, calcium=820, water=1800),
     "벗어난 항목이 없다. 여기서 '관리가 필요하다'고 하면 지어낸 것이다."),

    ("영양-여럿벗어남", "nutrition",
     _nutrition(30, seed=23, calories=2100, carbohydrate=240, protein=78, total_fat=88,
                saturated_fat=30, sodium=3600, sugar=42, dietary_fiber=15,
                potassium=2000, calcium=600, water=1850),
     "벗어난 항목이 여럿이다. 넉 줄 안에 몇 개나 담는지 본다."),

    ("생체-하나만벗어남", "bio",
     _bio(30, seed=31, systolic=112, diastolic=72, glucose=108, bmi=21.5, heart_rate=72),
     "공복 혈당 하나만 벗어났다. 하나뿐일 때도 놓치면 커버리지 지표가 무의미하다."),

    ("생체-혈압상승", "bio",
     _bio(26, seed=41, step=7, drift=0.18, spread=0.025,
          systolic=126, diastolic=80, glucose=94, bmi=23.0, heart_rate=70),
     "혈압이 반년에 걸쳐 오른다. 오르는 흐름을 짚는지, 흐름과 수준을 가려 말하는지 본다."),

    ("생체-기록드묾", "bio",
     _bio(3, seed=51, step=14, systolic=132, diastolic=86, glucose=104,
          bmi=24.0, heart_rate=78),
     "여섯 주 사이에 세 번 쟀을 뿐이다. 신뢰도가 '부족'인데 추세를 단정하는지 본다."),

    ("수면-구성문제", "sleep",
     _sleep(30, seed=61, score=85, deep=40, light=330, rem=90, awake=20),
     "여덟 시간을 자고 점수도 높은데 깊은잠 비중이 낮다. 길이와 구성을 가려 말하는지 본다."),

    ("활동-들쭉날쭉", "activity",
     _activity(60, seed=71, steps=8200, calories=380, workout_every=3, minutes=45,
               spread=0.62, spike=2.4),
     "걸음 수가 날마다 크게 출렁이고 하루는 튄다. 평균보다 꾸준함을 먼저 말하는지 본다."),

    ("활동-운동드묾", "activity",
     _activity(60, seed=81, steps=9000, calories=380, workout_every=7, minutes=40),
     "걸음은 넉넉하고 운동은 한 번에 40분씩 주 1회다. 길이가 아니라 횟수가 모자란 경우다."),
)


def ground_truth(domain: str, window: dict[str, Any]) -> dict[str, Any]:
    """코드가 계산한 판정. 이것이 정답지다."""
    from app.services.lifestyle_report import LifestyleReportService, _prompt_view

    view = _prompt_view(LifestyleReportService.build_analysis(domain, window))
    signals = lambda metric: metric.get("recent") or metric.get("full") or {}
    return {
        "off_range": [{"metric": m["metric"], "level": signals(m).get("level"),
                       "frequency": signals(m).get("frequency")}
                      for m in view["metrics"] if "벗어남" in signals(m).get("level", "")],
        "moving": [{"metric": m["metric"],
                    "full": (m.get("full") or {}).get("direction"),
                    "recent": (m.get("recent") or {}).get("direction")}
                   for m in view["metrics"]
                   if "흐름" in ((m.get("full") or {}).get("direction", "")
                                + (m.get("recent") or {}).get("direction", ""))],
        "unstable": [m["metric"] for m in view["metrics"]
                     if signals(m).get("stability") == "날마다 편차가 큼"],
        "low_confidence": [m["metric"] for m in view["metrics"]
                           if signals(m).get("confidence") == "부족"],
        "anomalies": [m["metric"] for m in view["metrics"] if m.get("example_day")],
        "separately_measured": [key for key in ("sleep_timing", "exercise_habit", "meal_pattern")
                                if view.get(key)],
    }


def export(target: Path) -> None:
    """기록과 정답지를 한 줄에 하나씩 남긴다."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        for name, domain, window, intent in CASES:
            file.write(json.dumps({
                "case": name,
                "domain": domain,
                "intent": intent,
                # 정답지는 코드가 계산한 값을 뜬 것이다. 참고범위를 고치면 낡는다.
                "expected": {"snapshot_at": f"{datetime.now():%Y-%m-%d}",
                             **ground_truth(domain, window)},
                "window": window,
            }, ensure_ascii=False) + "\n")
    rows = sum(len(source["rows"]) for _, _, window, _ in CASES for source in window.values())
    print(f"구간 {len(CASES)}개 · 기록 {rows}건 → {target}")
    print("   정답지는 코드가 계산한 스냅샷이다. 참고범위를 고치면 다시 떠야 한다.")


def describe(name: str, domain: str, window: dict[str, Any], intent: str) -> None:
    """한 구간의 정답지를 사람이 읽게 찍는다."""
    from app.services.lifestyle_report import DOMAIN_LABELS

    truth = ground_truth(domain, window)
    print(f"[{name}]  {DOMAIN_LABELS[domain]}")
    print(f"   겨누는 것 : {intent}")
    off = truth["off_range"]
    listed = " · ".join(f"{item['metric']}({'크게' if '크게' in item['level'] else '조금'})"
                        for item in off)
    print(f"   벗어남    : {len(off)}개  {listed or '없음'}")
    moving = " · ".join(
        f"{item['metric']}(전체 {item['full']}"
        + (f" · 최근 {item['recent']}" if item["recent"] else "") + ")"
        for item in truth["moving"])
    for label, shown in (("움직임    ", moving),
                         ("들쭉날쭉  ", " · ".join(truth["unstable"])),
                         ("신뢰도부족", " · ".join(truth["low_confidence"])),
                         ("이상 지점 ", " · ".join(truth["anomalies"])),
                         ("따로 잰 값", " · ".join(truth["separately_measured"]))):
        if shown:
            print(f"   {label}: {shown}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", nargs="?", const="", default=None, metavar="경로",
                        help="기록과 정답지를 jsonl로 뜬다. 경로를 비우면 eval_data에 쓴다")
    args = parser.parse_args()
    if args.export is not None:
        export(Path(args.export) if args.export
               else ROOT / "evaluation" / "eval_data" / "lifestyle_cases.jsonl")
        return

    print("합성 구간과 코드가 계산한 정답지 — 모델 호출 없음\n")
    for case in CASES:
        describe(*case)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
