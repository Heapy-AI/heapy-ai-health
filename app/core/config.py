# 설정을 한 곳에 모은다(바꾸면 전체 반영)
import os
from pathlib import Path
from dotenv import load_dotenv

# app/ 폴더를 위로 거슬러 찾아 ROOT 를 잡는다(어디서 실행해도 경로가 맞게)
def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "app").is_dir() and (
            (p / "README.md").exists() or (p / "requirements.txt").exists()
        ):
            return p
    # 루트 대체안으로 패키지 위치에서 상위 2단계(레포 루트)를 반환한다.
    fallback = start.parents[2] if len(start.parents) >= 3 else start
    print(
        f"[config] 'app' 폴더를 찾지 못했습니다. {fallback}을(를) ROOT로 사용합니다."
    )
    return fallback

ROOT = _find_root(Path(__file__).resolve().parent)
DATA = ROOT / "data"
CHUNK_ROOT = ROOT / "vdb" / "chunk"

load_dotenv(ROOT / ".env")                 # .env 의 GEMINI_API_KEY / GOOGLE_API_KEY 읽기
load_dotenv()                              # 현재 작업 폴더의 .env 도 한 번 더(보강)

# LangChain 의 Google 연동은 GOOGLE_API_KEY 를 봅니다 — 없으면 GEMINI_API_KEY 로 채웁니다.
google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not google_key:
    raise RuntimeError(
        "GOOGLE_API_KEY 또는 GEMINI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요."
    )
os.environ["GOOGLE_API_KEY"] = google_key

MODEL = "gemini-2.5-flash"                     # 답변 생성에 쓸 모델 이름
EMBED_MODEL = "jhgan/ko-sroberta-multitask"    # 한국어 무료 임베딩(API 비용 0)
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "").strip()
PINECONE_INDEX_NAME = os.environ.get(
    "PINECONE_INDEX_NAME",
    "heapy-rag",
).strip()
PINECONE_DIMENSION = 768
PINECONE_METRIC = "cosine"
SEARCH_TOP_K = 3


def _positive_int_env(name: str, default: int) -> int:
    """양의 정수 환경변수를 읽는다.

    작성자: 김진우
    """
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name}은 1 이상의 정수여야 합니다.")
    return value


def _non_negative_float_env(name: str, default: float) -> float:
    """0 이상의 실수 환경변수를 읽는다.

    작성자: 김진우
    """
    value = float(os.environ.get(name, str(default)))
    if value < 0.0:
        raise RuntimeError(f"{name}은 0 이상의 실수여야 합니다.")
    return value

_intent_model_value = os.environ.get(
    "INTENT_MODEL_PATH",
    "model/classifier/artifacts/intent-v7/best_model.json",
)
INTENT_MODEL_PATH = Path(_intent_model_value)
if not INTENT_MODEL_PATH.is_absolute():
    INTENT_MODEL_PATH = ROOT / INTENT_MODEL_PATH
INTENT_MIN_CONFIDENCE = float(os.environ.get("INTENT_MIN_CONFIDENCE", "0.55"))

# vdb/chunk의 하위 폴더를 Pinecone namespace로 사용한다.
if CHUNK_ROOT.exists():
    COLLECTIONS = {
        path.name: path
        for path in CHUNK_ROOT.iterdir()
        if path.is_dir()
    }
else:
    COLLECTIONS = {}

# 모듈 import 중 외부 네트워크를 호출하지 않고 설정값만으로 검색 대상을 확정한다.
# 운영 환경에서는 SEARCH_COLLECTIONS로 명시적으로 덮어쓸 수 있다.
# 작성자: 김진우
_default_search_collections = tuple(COLLECTIONS) or (
    "health_checkup_info",
    "disease_info",
    "medication_info",
)
_search_collections_value = os.environ.get(
    "SEARCH_COLLECTIONS",
    ",".join(_default_search_collections),
)
SEARCH_COLLECTIONS = tuple(
    dict.fromkeys(
        collection.strip()
        for collection in _search_collections_value.split(",")
        if collection.strip()
    )
)

# 데이터 적재 완료 후 평가를 통해 조정한다. 현재 값은 구조 검증용 기본값이다.
SEARCH_TOP_K_PER_COLLECTION = _positive_int_env(
    "SEARCH_TOP_K_PER_COLLECTION",
    10,
)
SEARCH_FINAL_TOP_K = _positive_int_env("SEARCH_FINAL_TOP_K", 6)
SEARCH_MAX_PER_COLLECTION = _positive_int_env(
    "SEARCH_MAX_PER_COLLECTION",
    6,
)
SEARCH_MIN_SCORE = _non_negative_float_env("SEARCH_MIN_SCORE", 0.0)

# 멀티턴 질문 재작성과 요약 메모리는 클라이언트가 전달한 문맥만 사용한다.
# 작성자: 김진우
CHAT_HISTORY_MAX_TURNS = _positive_int_env("CHAT_HISTORY_MAX_TURNS", 6)
CHAT_HISTORY_MAX_CHARS = _positive_int_env("CHAT_HISTORY_MAX_CHARS", 600)
QUERY_REWRITE_ENABLED = os.environ.get("QUERY_REWRITE_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
}
CONVERSATION_SUMMARY_ENABLED = os.environ.get(
    "CONVERSATION_SUMMARY_ENABLED",
    "1",
).strip().lower() not in {"0", "false"}
CONVERSATION_SUMMARY_MAX_CHARS = _positive_int_env(
    "CONVERSATION_SUMMARY_MAX_CHARS",
    400,
)

# 의료용어 정규화 저장소와 후보 판정 기준이다.
# 작성자: 김진우
RDB_DSN = (
    os.environ.get("RDB_DSN")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()
QUERY_RESOLUTION_MIN_SCORE = float(
    os.environ.get("QUERY_RESOLUTION_MIN_SCORE", "0.66")
)
if not 0.0 <= QUERY_RESOLUTION_MIN_SCORE <= 1.0:
    raise RuntimeError("QUERY_RESOLUTION_MIN_SCORE는 0 이상 1 이하이어야 합니다.")
QUERY_RESOLUTION_AMBIGUITY_MARGIN = _non_negative_float_env(
    "QUERY_RESOLUTION_AMBIGUITY_MARGIN",
    0.05,
)

# Supabase Auth는 공개 가능한 publishable key(또는 기존 anon key)를 사용한다.
# 작성자: 김진우
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_PUBLISHABLE_KEY = (
    os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or ""
).strip()
AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "0").strip().lower() in {
    "1",
    "true",
}

# 생활습관 컨텍스트는 날짜 필터 없이 최신순 건수 제한으로만 조회한다.
# 기기 연동이 끊겨 데이터가 낡아도 최근 기록은 계속 조회되도록 하기 위함이다.
LIFESTYLE_CONTEXT_ENABLED = os.environ.get(
    "LIFESTYLE_CONTEXT_ENABLED",
    "1",
).strip().lower() not in {"0", "false"}
LIFESTYLE_CONTEXT_MAX_ROWS = _positive_int_env("LIFESTYLE_CONTEXT_MAX_ROWS", 10)
LIFESTYLE_CONTEXT_TREND_MAX_ROWS = _positive_int_env(
    "LIFESTYLE_CONTEXT_TREND_MAX_ROWS",
    30,
)
PERSONAL_DATA_WINDOW_DAYS = _positive_int_env("PERSONAL_DATA_WINDOW_DAYS", 7)
PERSONAL_DATA_MAX_ROWS = _positive_int_env("PERSONAL_DATA_MAX_ROWS", 500)
