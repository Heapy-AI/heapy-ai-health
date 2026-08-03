# 설정을 한 곳에 모은다(바꾸면 전체 반영) - 03·04강 '설정 주도'
import os
from pathlib import Path
from dotenv import load_dotenv

# data/ 폴더를 위로 거슬러 찾아 ROOT 를 잡는다(어디서 실행해도 경로가 맞게)
def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "data").exists():
            return p
    raise RuntimeError(f"'data' 폴더를 찾을 수 없습니다. (탐색 시작 위치: {start})")

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
    "classifier/artifacts/intent-v6/best_model.json",
)
INTENT_MODEL_PATH = Path(_intent_model_value)
if not INTENT_MODEL_PATH.is_absolute():
    INTENT_MODEL_PATH = ROOT / INTENT_MODEL_PATH
INTENT_MIN_CONFIDENCE = float(os.environ.get("INTENT_MIN_CONFIDENCE", "0.55"))

# vdb/chunk의 하위 폴더를 Pinecone namespace로 사용한다.
COLLECTIONS = {
    path.name: path
    for path in CHUNK_ROOT.iterdir()
    if path.is_dir()
}

_search_collections_value = os.environ.get(
    "SEARCH_COLLECTIONS",
    ",".join(COLLECTIONS),
)
SEARCH_COLLECTIONS = tuple(
    dict.fromkeys(
        collection.strip()
        for collection in _search_collections_value.split(",")
        if collection.strip()
    )
)
if not SEARCH_COLLECTIONS:
    raise RuntimeError(
        "SEARCH_COLLECTIONS가 비어 있습니다. 검색할 Pinecone namespace를 설정하세요."
    )

# 데이터 적재 완료 후 평가를 통해 조정한다. 현재 값은 구조 검증용 기본값이다.
SEARCH_TOP_K_PER_COLLECTION = _positive_int_env(
    "SEARCH_TOP_K_PER_COLLECTION",
    SEARCH_TOP_K,
)
SEARCH_FINAL_TOP_K = _positive_int_env("SEARCH_FINAL_TOP_K", 6)
SEARCH_MAX_PER_COLLECTION = _positive_int_env(
    "SEARCH_MAX_PER_COLLECTION",
    2,
)
SEARCH_MIN_SCORE = _non_negative_float_env("SEARCH_MIN_SCORE", 0.0)
