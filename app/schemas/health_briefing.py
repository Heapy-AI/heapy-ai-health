"""홈 화면 '오늘의 AI 건강 브리핑' 출력 계약 (프롬프트 v1.0).

내건강 탭의 분석과 쓰임이 다르다. 탭은 **왜 그런지를 설명**하고, 홈은 앱을 열자마자
보이는 자리라 **한 줄 요약과 다음 행동**만 담는다. 같은 말을 두 번 하면 사용자가 둘 중
하나를 안 읽는다.

숫자를 담는 자리를 두지 않는다. `metric`·`change`는 서비스가 세어 붙인다. 모델이 적은
수치를 그대로 화면에 내보내면 틀린 값을 사용자가 읽게 된다.

작성자: 고수연
"""

from typing import Literal

from pydantic import BaseModel, Field


class BriefingSection(BaseModel):
    """한 갈래에 대한 한 줄. 모델은 말과 판단만 낸다."""

    # 앱의 영역 아이콘·색이 이 키에 붙는다. 근거가 없는 키는 서비스가 버린다.
    key: Literal["score", "sleep", "activity", "nutrition", "bio"]
    # 수치를 적지 않는다. 화면에서 metric 옆에 놓이므로 같은 숫자를 두 번 쓰게 된다.
    text: str = Field(..., max_length=60)
    # 칩 색을 정한다. 오르는 것이 늘 좋은 것은 아니라 방향(↑↓) 대신 판단을 받는다.
    # 체중이 늘었을 때 ↑를 초록으로 칠할 수는 없다.
    tone: Literal["good", "watch", "neutral"]


class BriefingContent(BaseModel):
    """하루 한 건의 브리핑 본문.

    길이 상한은 화면에서 왔다. headline은 18px 두 줄, body는 상세 화면의 한 문단이다.
    다만 상한을 화면 너비에 딱 맞추지는 않았다. `max_retries=0`이라 검증에 걸리면 그날
    브리핑이 통째로 실패한다. 목표 길이는 프롬프트가 말하고, 여기서는 넘치지만 않게 막는다.
    """

    headline: str = Field(..., max_length=40)
    body: str = Field(..., max_length=120)
    # 3~5개를 요청하지만 기록이 모자라면 줄어든다. 하한을 두면 그날 브리핑이 실패한다.
    sections: list[BriefingSection] = Field(default_factory=list, max_length=5)
