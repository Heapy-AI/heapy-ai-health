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
PERSIST_DIR = str(ROOT / "vdb" / "chroma")     # Chroma 영속화 폴더 (지난 구조 논의와 일치)
DOCS_DIR = DATA / "disease_info"               # 질병정보 원천 문서 폴더

# Chroma DB collection name
COLLECTIONS = {
    "disease_info": DATA / "disease_info",
    "health_checkup_info": DATA / "health_checkup_info",
    # "medication_info": DATA / "medication_info",
    # "lifestyle_info": DATA / "lifestyle_info",   # 추가
}