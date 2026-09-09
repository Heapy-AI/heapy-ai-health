"""판정 기준 문서와 코드가 어긋나지 않는지 지킨다.

참고범위는 값 하나를 고치면 코드·문서·화면 세 곳이 함께 움직여야 한다. 한 곳만
고치면 화면이 사실과 다른 잣대를 말하게 되므로, 문서의 표를 읽어 코드와 대조한다.

문서: docs/생활건강_AI해석_판정기준_출처와_적용.md

작성자: 고수연
"""

import re
import unittest
from pathlib import Path

from app.services.lifestyle_report import (
    _DOMAIN_METRICS,
    _ENERGY_CAUTION_MARGIN,
    _ENERGY_GOOD_MARGIN,
    _INTAKE_CAUTION_RATIO,
    _KDRI_2025,
    domain_metrics,
)


DOC = (Path(__file__).resolve().parents[1] / "docs"
       / "생활건강_AI해석_판정기준_출처와_적용.md")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _read(text: str) -> str:
    return DOC.read_text(encoding="utf-8")


def _section(title: str) -> str:
    """제목 아래부터 다음 제목 전까지."""
    body = DOC.read_text(encoding="utf-8")
    start = body.index(title) + len(title)
    rest = body[start:]
    end = rest.find("\n### ")
    tail = rest.find("\n## ")
    if 0 <= tail < (end if end >= 0 else len(rest)):
        end = tail
    return rest[:end] if end >= 0 else rest


def _rows(section: str) -> list[list[str]]:
    """첫 표의 본문 행만. 한 절에 표가 여럿이면 앞의 것만 본다."""
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:
                break
            continue
        if set(line) <= set("|-: "):
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows[1:] if rows else []


def _numbers(text: str) -> list[float]:
    return [float(value) for value in _NUMBER.findall(text.replace(",", ""))]


class ReferenceCriteriaDocTest(unittest.TestCase):
    """문서가 코드의 실제 판정값을 그대로 적고 있는지 본다."""

    def test_sex_and_age_tables_match_the_code(self) -> None:
        """성별·연령대 표 40칸이 코드의 섭취기준 표와 같아야 한다."""
        tables = {
            "### 에너지필요추정량 (kcal/일)": "energy",
            "### 단백질 권장섭취량 (g/일)": "protein",
            "### 식이섬유 충분섭취량 (g/일)": "fiber",
            "### 칼슘 권장섭취량 (mg/일)": "calcium",
        }
        bands = ("19-29", "30-49", "50-64", "65-74", "75+")
        for title, key in tables.items():
            rows = _rows(_section(title))
            self.assertEqual(len(rows), len(bands), f"{title} 행 수")
            for band, row in zip(bands, rows):
                for sex, cell in (("male", row[1]), ("female", row[2])):
                    with self.subTest(table=key, band=band, sex=sex):
                        self.assertEqual(_numbers(cell)[0], _KDRI_2025[sex][band][key])

    def test_margins_the_service_chose_are_written_down(self) -> None:
        """섭취기준이 정하지 않은 값이라 어디선가 조용히 바뀌면 안 된다."""
        section = _section("### 위 값을 판정 문턱으로 옮기는 규칙")

        self.assertIn(f"±{_ENERGY_GOOD_MARGIN:.0%}".replace("%", "%"), section)
        self.assertIn(f"±{_ENERGY_CAUTION_MARGIN:.0%}", section)
        self.assertIn(f"{_INTAKE_CAUTION_RATIO:.0%}", section)

    def test_every_metric_row_matches_the_code(self) -> None:
        """탭별 판정값 표가 코드의 항목 정의와 같아야 한다."""
        sections = {
            "bio": "### 생체기록 — 전체 180일 · 최근 30일",
            "activity": "### 활동기록 — 전체 90일 · 최근 30일",
            "nutrition": "### 영양기록 — 전체 90일 · 최근 30일",
            "sleep": "### 수면기록 — 전체 90일 · 최근 30일",
        }
        direction = {"채울수록 좋음": "higher", "낮을수록 좋음": "lower",
                     "적정 범위": "range", "추세만": "trend"}
        for domain, title in sections.items():
            listed = {}
            for row in _rows(_section(title)):
                # 한 줄에 여러 항목을 묶어 적은 행(깊은수면·얕은수면·REM수면)은 넘긴다.
                for name in row[0].split(" · "):
                    listed[name.strip()] = row
            for metric in _DOMAIN_METRICS[domain]:
                with self.subTest(domain=domain, metric=metric.label):
                    row = listed.get(metric.label)
                    self.assertIsNotNone(row, f"{metric.label} 행이 문서에 없다")
                    self.assertEqual(direction[row[2]], metric.direction)
                    good, caution = _numbers(row[3]), _numbers(row[4])
                    if metric.direction == "trend":
                        self.assertEqual(good, [])
                        continue
                    bounds = [value for value in (metric.low, metric.high) if value is not None]
                    self.assertEqual(good, bounds, "양호 범위")
                    edges = [value for value in (metric.caution_low, metric.caution_high)
                             if value is not None]
                    self.assertEqual(caution, edges, "주의 범위")

    def test_documented_metrics_are_not_stale(self) -> None:
        """문서에만 남고 코드에서 사라진 항목이 없어야 한다."""
        sections = {
            "bio": "### 생체기록 — 전체 180일 · 최근 30일",
            "activity": "### 활동기록 — 전체 90일 · 최근 30일",
            "nutrition": "### 영양기록 — 전체 90일 · 최근 30일",
            "sleep": "### 수면기록 — 전체 90일 · 최근 30일",
        }
        for domain, title in sections.items():
            listed = set()
            for row in _rows(_section(title)):
                listed.update(name.strip() for name in row[0].split(" · "))
            with self.subTest(domain=domain):
                self.assertEqual(listed, {m.label for m in _DOMAIN_METRICS[domain]})

    def test_the_footnote_wording_matches_the_service(self) -> None:
        """각주는 사용자가 보는 말이다. 문서에 적힌 그대로 나가야 한다."""
        from app.services.lifestyle_report import reference_basis

        rows = _rows(_section("### 어느 잣대로 쟀는지 화면에 밝힌다"))
        cases = ((None, None), ("Male", None), ("Male", 40))
        for (sex, age), row in zip(cases, rows):
            with self.subTest(sex=sex, age=age):
                # 문서는 '참고범위는 ~습니다' 꼴로 적고, 서비스는 그 가운데 토막만 만든다.
                self.assertIn(reference_basis(sex, age).replace("않음", ""), row[1])

    def test_sources_name_where_each_number_came_from(self) -> None:
        """어느 기관의 무슨 문서인지 없으면 나중에 고칠 수가 없다."""
        body = DOC.read_text(encoding="utf-8")

        for source in ("2025 한국인 영양소 섭취기준", "보건복지부", "한국영양학회",
                       "WHO 나트륨 권고", "미국수면재단", "대한고혈압학회",
                       "대한비만학회", "대한당뇨병학회"):
            with self.subTest(source=source):
                self.assertIn(source, body)
        # 확인한 것에는 열어 볼 수 있는 주소가 있어야 한다.
        self.assertGreaterEqual(body.count("https://"), 4)
        # 우리가 정한 값과 기준이 정한 값을 갈라 두었는지.
        self.assertIn("서비스가 정한 값", body)
        self.assertIn("기기 제조사 자체 기준", body)

    def test_defaults_are_the_loosest_of_the_sexes(self) -> None:
        """성별을 모를 때의 값이 남녀 어느 쪽에도 엄하지 않아야 한다.

        문서가 약속한 규칙이다. 채울수록 좋은 항목은 가장 낮은 권장량,
        적정 범위 항목은 모든 연령대를 감싸는 폭을 쓴다.
        """
        base = {m.label: m for m in _DOMAIN_METRICS["nutrition"]}
        for sex in ("male", "female"):
            for age in (25, 40, 55, 70, 80):
                metrics = {m.label: m for m in domain_metrics("nutrition", sex, age)}
                for name in ("단백질", "식이섬유", "칼슘"):
                    with self.subTest(sex=sex, age=age, metric=name):
                        self.assertLessEqual(base[name].low, metrics[name].low)
                with self.subTest(sex=sex, age=age, metric="섭취칼로리"):
                    self.assertLessEqual(base["섭취칼로리"].low, metrics["섭취칼로리"].low)
                    self.assertGreaterEqual(base["섭취칼로리"].high, metrics["섭취칼로리"].high)


if __name__ == "__main__":
    unittest.main()
