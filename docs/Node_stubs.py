"""
Healpy AI health care 파이프라인 — 노드별 함수 시그니처 (분업 개발용)

각 노드는 파이프라인 State에서 필요한 필드를 읽고, 결과 필드를 갱신한다.
아래 스텁은 "이 노드가 무슨 타입을 받아 무슨 타입을 내보내는지"를 명시하기 위한 것이다.
담당자는 자기가 맡은 함수의 인자 타입과 반환 타입만 맞추면 된다.

[전제]
- 판정 기준(Labs Item Master)은 이 파이프라인 범위에서 고정(안 바뀜).
- Labs Records의 status는 저장 시점에 이미 판정된 값. 조회 파이프라인은 읽기만 함.
- 기준 변경 시 과거 데이터 재판정은 별도 마이그레이션 배치 담당 (이 문서 범위 밖).
- 노드 간 전달: 메모리상 State 객체 참조 (직렬화 없음).
  직렬화는 경계에서만 — 클라이언트 응답, vLLM 호출, Redis 저장.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ============================================================
# 열거형
# ============================================================

class Intent(str, Enum):
    SIMPLE_LOOKUP = "simple_lookup"
    COMPREHENSIVE = "comprehensive"
    GENERAL_CHAT = "general_chat"
    IGNORE = "ignore"


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Collection(str, Enum):
    """VDB collection. sub_intents는 이 값들의 목록이다."""
    HEALTH_CHECKUP = "health_checkup_info"      # 검사 항목 정의/해석 (단순조회·종합분석)
    DISEASE = "disease_info"                     # 질환 설명, 증상
    MEDICATION = "medication_info"               # 약물 정보, 부작용, 상호작용
    LIFESTYLE = "lifestyle_interventions"        # 생활습관, 식단, 운동


class Status(str, Enum):
    """검진 판정 (저장 시점에 확정됨)."""
    NORMAL_A = "정상"        # 정상A
    BORDERLINE = "경계"      # 정상B(경계)
    SUSPECT = "이상"         # 질환의심


# ============================================================
# VDB — 검색 결과 청크
# ============================================================

@dataclass
class ChunkMetadata:
    primary_key: str                       # 검사 항목명/질환명 등 (예: "Hb")
    categories: list[str]                  # 예: ["혈액"]
    source: str                            # 출처 (예: "질병관리청")
    created_at: str                        # 생성일 (예: "2024-01-15")
    related_diseases: list[str] = field(default_factory=list)
    related_items: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    """VDB 검색 결과. 실제 저장 구조는 text + metadata.
    score/collection은 검색 런타임에 부여됨 (스키마엔 없음)."""
    text: str
    metadata: ChunkMetadata
    collection: Collection                 # 어느 collection에서 왔는지 (런타임)
    score: float                           # 유사도 (런타임)

# 예시:
#   Chunk(
#       text="혈색소(Hb)는 적혈구에 포함된 단백질로 산소를 운반합니다. 정상 범위는 "
#            "남성 13.0-16.5 g/dL, 여성 12.0-15.5 g/dL입니다. ...",
#       metadata=ChunkMetadata(
#           primary_key="Hb",
#           categories=["혈액"],
#           source="질병관리청",
#           created_at="2024-01-15",
#           related_diseases=["빈혈", "철결핍성빈혈"],
#           related_items=["RBC", "Ferritin"],
#       ),
#       collection=Collection.HEALTH_CHECKUP,
#       score=0.87,
#   )


# ============================================================
# RDB — 개인 컨텍스트 (comprehensive 전용, 캐시 금지)
# ============================================================

@dataclass
class UserProfile:
    """Users 테이블."""
    user_id: str
    name: str
    birth_date: str                        # YYYY-MM-DD
    gender: str                            # "M" | "F"
    chronic_conditions: list[str] = field(default_factory=list)


@dataclass
class LabItem:
    """Labs Records.items 의 개별 수치. status는 저장 시점 판정값."""
    item_name: str                         # 예: "Hb"
    value: float | str
    status: Status


@dataclass
class LabRecord:
    """Labs Records 한 건."""
    record_id: str
    user_id: str
    measured_at: str                       # YYYY-MM-DD
    items: list[LabItem]


@dataclass
class UserContext:
    """D2가 조합한 개인 컨텍스트. 판정 로직 없음 — 저장된 값 조회·조합만."""
    profile: UserProfile
    records: list[LabRecord]               # 검진 이력 (measured_at 최신순 정렬).
                                           # records[0]=최신. 추이 질문("지난번보다?") 대응.
                                           # 조회 범위(최근 N건/전체)는 D2에서 정책 결정.

# 예시 (검진 2건 — 추이 질문 대응):
#   UserContext(
#       profile=UserProfile(
#           user_id="user_001",
#           name="고수연",
#           birth_date="1990-05-20",
#           gender="F",
#           chronic_conditions=[],
#       ),
#       records=[
#           LabRecord(                                  # records[0] = 최신
#               record_id="lab_002",
#               user_id="user_001",
#               measured_at="2026-07-13",
#               items=[
#                   LabItem("Hb", 12.8, Status.NORMAL_A),
#                   LabItem("AST", 15, Status.NORMAL_A),
#                   LabItem("SBP", 130, Status.BORDERLINE),
#               ],
#           ),
#           LabRecord(                                  # records[1] = 직전
#               record_id="lab_001",
#               user_id="user_001",
#               measured_at="2026-01-10",
#               items=[
#                   LabItem("Hb", 13.5, Status.NORMAL_A),
#                   LabItem("AST", 15, Status.NORMAL_A),
#                   LabItem("SBP", 122, Status.BORDERLINE),
#               ],
#           ),
#       ],
#   )


# ============================================================
# Turn — 멀티턴 히스토리
# ============================================================

@dataclass
class Turn:
    role: Role
    content: str
    timestamp: datetime


# chunks 필드의 3가지 상태 (전 팀 합의 필수):
#   None       -> 검색 인프라 실패 (VDB 타임아웃/재시도 초과) -> 에러 분기
#   []         -> 검색 성공, 결과 0건 -> 일반 대화(general_chat) 전환
#   [Chunk...] -> 정상 -> 프롬프트 구성으로
# 타입: list[Chunk] | None


# ============================================================
# 세션 · 컨텍스트 관리
# ============================================================

def s1_get_session(raw_query: str) -> str:
    """세션 조회 (저장 X, 조회만). 반환: session_id"""
    ...

def s1chk_is_new(session_id: str) -> bool:
    """기존 세션 존재 여부. 반환: is_new_session"""
    ...

def s2_load_context(session_id: str) -> tuple[list[Turn], str | None]:
    """기존 세션의 히스토리 + 요약 로드. 반환: (history, summary)
    summary는 직전 턴의 O3가 만들어 둔 것을 읽기만 함 (여기서 생성 X)."""
    # 예시 반환:
    #   ([Turn(Role.USER, "AST 수치가 뭐야?", ...),
    #     Turn(Role.ASSISTANT, "AST는 간 효소로...", ...)],
    #    "사용자는 간 기능 수치(AST)에 대해 문의함")
    ...

def s3_reformulate(
    raw_query: str,
    history: list[Turn],
    summary: str | None,
) -> str:
    """대명사/생략 복원. 반환: resolved_query"""
    # 예시: raw_query="그럼 정상 범위는?" + history(직전에 AST 문의)
    #   -> resolved_query="AST 수치의 정상 범위는?"
    ...

def s4_init_new_session(raw_query: str) -> tuple[str, list[Turn]]:
    """신규 세션 초기화. 재구성 스킵.
    반환: (resolved_query=raw_query 그대로, history=[])"""
    ...


# ============================================================
# 의도 분류 (Decider)
# ============================================================

def a1_embed(resolved_query: str) -> list[float]:
    """Sentence-Transformers 임베딩. 반환: query_embedding
    ★ 이 벡터는 캐시조회/검색/캐시저장에서 재사용됨. 재계산 금지."""
    # 예시: "AST 수치가 뭐야?" -> [0.0234, -0.117, 0.052, ...] (예: 768차원)
    ...

def a4_classify_intent(query_embedding: list[float]) -> Intent:
    """A2(Linear) + A3(Softmax) 거쳐 intent 결정. 반환: intent

    [분류 기준]
      simple_lookup : 개인 데이터 불필요, VDB 검색만으로 답 가능 (용어/정의)
      comprehensive : 개인 데이터(검진 수치 / 생활 / 복용금지 등) 필요 + 분석
      general_chat  : 건강 관련이나 검색·분석 불필요, 대화성
      ignore        : 건강 무관 또는 상담 범위 초과

    [분류 fixture — 학습/평가용]
      Q1  "Hb가 뭐예요?"                          -> SIMPLE_LOOKUP  (용어: 건강검진)
      Q2  "Metformin이 뭐예요?"                    -> SIMPLE_LOOKUP  (용어: 약물)
      Q3  "Metformin이랑 철분제 같이 먹어도 돼?"    -> COMPREHENSIVE  (약물상호작용 + 개인 복용금지 대조)
      Q4  "최근 AST가 높은데 왜?"                  -> COMPREHENSIVE  (정보 + 개인 검진 데이터)
      Q5  "요즘 피곤한데 뭐가 원인일까?"           -> COMPREHENSIVE  (정보 + 검진 + 생활 데이터)
      Q6  "날씨 좋다 오늘 운동하면 딱이다"          -> GENERAL_CHAT   (건강 관련, 검색 불필요)
      Q7  "요즘 업무가 스트레스가 많아요."          -> GENERAL_CHAT   (건강 관련, 검색 불필요)
      Q8  "오늘 날씨 뭐야?"                        -> IGNORE         (건강 무관)
      Q9  "너 누구야? 어디서 만들어진 거야?"        -> IGNORE         (건강 무관)
      Q10 "암 치료법을 알려줄래?"                   -> IGNORE         (상담 범위 초과)

    ※ simple vs comprehensive의 실질 기준은 "개인 데이터를 쓰는가".
      Q3는 일반 약물 지식만이 아니라 사용자별 복용금지 목록과 대조해야 하므로 comprehensive.
    """
    ...


# ============================================================
# 검색 (simple / comprehensive 공통 패턴)
# ============================================================

def b1_classify_subintent(resolved_query: str, intent: Intent) -> list[Collection]:
    """comprehensive 전용. 다중 선택. 반환: sub_intents = 검색할 collection 목록

    [예시 — comprehensive 쿼리별 collection 선택]
      Q3 "Metformin이랑 철분제 같이 먹어도 돼?" -> [MEDICATION]
         (+ 개인 복용금지 목록은 RDB에서 별도 조회)
      Q4 "최근 AST가 높은데 왜?"               -> [HEALTH_CHECKUP, DISEASE]
         (+ 개인 검진 수치는 RDB에서 조회)
      Q5 "요즘 피곤한데 뭐가 원인일까?"          -> [HEALTH_CHECKUP, DISEASE, LIFESTYLE]
         (+ 개인 검진 + 생활 데이터는 RDB에서 조회)
    ※ VDB collection 선택과 별개로, 어떤 RDB 개인 데이터를 조회할지도
      sub_intent에 따라 D2에서 결정 (필요한 테이블만 조회).
    """
    ...

def cache_lookup(query_embedding: list[float]) -> tuple[bool, list[Chunk] | None]:
    """SC1 / BC1 캐시 조회. 유사도 >= threshold면 히트.
    반환: (cache_hit, chunks) — 히트 시 chunks 채움, 미스 시 None"""
    ...

def vdb_search(
    query_embedding: list[float],
    collections: list[Collection] | None = None,  # comprehensive만 지정, simple은 기본 collection
) -> list[Chunk] | None:
    """C1 / B2 VDB 검색 (top-k). 캐시 미스 시 실행.
    반환: chunks — 인프라 실패 시 None, 결과 없음 시 [] (위 상태 규약 준수)"""
    ...

def cache_store(query_embedding: list[float], chunks: list[Chunk]) -> None:
    """SC3 / BC3 캐시 저장 (TTL). Redis 기록. 청크만 저장(개인정보 X). 반환 없음."""
    ...


# ============================================================
# 개인 컨텍스트 (comprehensive 전용, 캐시 금지)
# ============================================================

def au1_check_auth(session_id: str) -> bool:
    """접근권한 확인. 반환: 인증 성공 여부"""
    ...

def d1_d2_collect_context(session_id: str) -> UserContext:
    """D1(RDB 조회) + D2(조합). 반환: user_context
    ★ 판정 로직 없음 — Labs Records의 status는 이미 판정된 값을 읽기만 함.
    ★ 캐시 금지 — 사용자/시점마다 달라짐.
    조합 대상: Users(프로필) + Labs Records(최신 검진, status 포함).
    부가정보(단위/한글명 등) 필요 시 Labs Item Master 조회 가능(판정엔 안 씀)."""
    ...


# ============================================================
# 프롬프트 구성 · LLM
# ============================================================

def c2_build_prompt_simple(chunks: list[Chunk], history: list[Turn]) -> str:
    """simple 프롬프트 구성. 반환: prompt"""
    ...

def b4_build_prompt_comprehensive(
    chunks: list[Chunk],
    user_context: UserContext,
    history: list[Turn],
    summary: str | None,
) -> str:
    """comprehensive 프롬프트 구성 (검색+개인+히스토리+분석지시). 반환: prompt"""
    ...

def c5_build_prompt_chat(history: list[Turn], summary: str | None) -> str:
    """자유 대화 프롬프트 구성. 반환: prompt"""
    ...

def l1_l3_stream_llm(prompt: str):
    """L1 호출(stream=True) → L2 토큰 생성 → L3 청크 전송.
    반환: 토큰 청크 제너레이터 (SSE로 클라이언트 전송)."""
    ...

def b5_validate(accumulated_response: str) -> str:
    """누적 응답 검증 (스키마/안전성). 반환: 검증된 응답"""
    ...