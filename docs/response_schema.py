"""
Heapy AI health care 파이프라인 — intent 분기별 최종 응답 구조

실제 응답 본문은 스트리밍(SSE)으로 나가지만, 아래는 스트리밍과 무관한 "논리적 응답 구조"를 정의한다.
(구현 시 본문 텍스트는 스트림으로, 메타 필드는 스트림 종료 후 별도 전송하는 식으로 나눠도 됨)

intent에 따라 응답 구조가 다르다:
  simple_lookup : 개인 데이터 없음. 정의 + 출처만.
  comprehensive : 개인 데이터 결합 + 분석 + (선택)후속 액션.
  general_chat  : 자유 대화 본문만.
  ignore        : 고정 문구만.

★ 개인 데이터(personal_data)가 들어가면 comprehensive다.
  "나 혈압 높나?"처럼 본인 수치를 봐야 하는 질문은 simple이 아니라 comprehensive.
  simple은 "혈압이 뭐예요?" 같은 개인화 없는 순수 정의.

★ personal_hook / 후속 액션(미션 유도 등)은 아직 미정.
  구조에만 optional 필드로 넣어둠. 도입 확정 시 채운다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class ResponseType(str, Enum):
    SIMPLE_LOOKUP = "simple_lookup"
    COMPREHENSIVE = "comprehensive"
    GENERAL_CHAT = "general_chat"
    IGNORE = "ignore"


# 공통 필드 (모든 응답 공유)
#   type    : ResponseType — 어느 분기로 처리됐는지
#   answer  : str          — 사용자에게 보이는 본문 (스트리밍되는 실제 텍스트)
#   sources : list[str]    — 근거 청크 ID 목록 (검색 없는 분기는 빈 목록)


# ============================================================
# simple_lookup — 개인 데이터 없음, 정의/정보만
# ============================================================
# Q 예시: "혈압이 뭐예요?" / "Metformin이 뭐예요?"
SIMPLE_LOOKUP_EXAMPLE = {
    "type": "simple_lookup",
    "answer": "혈압은 심장이 수축할 때의 수축기혈압(SBP)과 이완할 때의 "
              "이완기혈압(DBP)으로 측정되며, 혈관에 가해지는 압력을 나타냅니다.",
    "sources": ["health_checkup_info:SBP"],
    # 개인 데이터 없음. cache_hit 여부 등 메타를 붙일 수도 있음(선택).
    "meta": {"cache_hit": True}
}


# ============================================================
# comprehensive — 개인 데이터 결합 + 분석 + (선택)후속 액션
# ============================================================
# Q 예시: "나 혈압 높나?" / "최근 AST가 높은데 왜?"
COMPREHENSIVE_EXAMPLE = {
    "type": "comprehensive",
    "answer": "당신의 혈압은 수축기 145 / 이완기 92 mmHg로 정상범위를 초과했습니다. "
              "지속되면 고혈압으로 진행될 수 있어 생활습관 관리가 필요합니다.",
    "sources": ["health_checkup_info:SBP", "disease_info:고혈압"],
    "personal_data": {
        # RDB(개인 검진)에서 온 값. 캐시 안 함.
        "items": [
            {"item_name": "SBP", "value": 145, "status": "이상", "normal_range": "120미만"},
            {"item_name": "DBP", "value": 92,  "status": "이상", "normal_range": "80미만"}
        ],
        "measured_at": "2026-07-13"
    },
    # 후속 액션 — 미정. 도입 시 채움. 없으면 생략.
    "next_action": {
        "type": "mission_suggestion",          # 예: 미션 유도
        "hook": "관련 혈압 관리 미션을 만들어드릴까요?"
    },
    "meta": {"cache_hit": False, "sub_intents": ["health_checkup_info", "disease_info"]}
}


# ============================================================
# general_chat — 자유 대화, 검색/개인데이터 없음
# ============================================================
# Q 예시: "요즘 업무 스트레스가 많아요." / "날씨 좋다 운동하면 딱이다"
GENERAL_CHAT_EXAMPLE = {
    "type": "general_chat",
    "answer": "스트레스가 쌓이면 몸도 함께 지치기 쉬워요. 잠깐씩 걷거나 "
              "심호흡하는 것만으로도 도움이 됩니다.",
    "sources": [],       # 검색 안 함
    # 개인 데이터 없음, 후속 액션 없음
}


# ============================================================
# ignore — 고정 문구 (건강 무관 / 범위 초과)
# ============================================================
# Q 예시: "오늘 날씨 뭐야?" / "암 치료법 알려줘"
IGNORE_EXAMPLE = {
    "type": "ignore",
    "answer": "죄송합니다. 건강 관련 문의만 도와드릴 수 있어요.",
    "sources": [],
    # 고정 문구. LLM 호출조차 없을 수 있음.
}


# ============================================================
# 참고: 분기별 필드 유무 요약
# ============================================================
# 필드            | simple | comprehensive | general_chat | ignore
# ----------------|--------|---------------|--------------|--------
# type            |   O    |      O        |     O        |   O
# answer          |   O    |      O        |     O        |   O
# sources         |   O    |      O        |     [](빈)   |   [](빈)
# personal_data   |   X    |      O        |     X        |   X
# next_action     |   X    |   O(선택,미정) |     X        |   X
# meta            | 선택   |    선택        |    선택       |  선택
