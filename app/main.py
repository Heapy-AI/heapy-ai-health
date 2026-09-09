from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.runtime import lifespan
from app.routers import ask, auth, chat, checkup_report, conversations, intent, personal_data

app = FastAPI(title="HEAPY RAG 서빙", version="1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(personal_data.router)
app.include_router(checkup_report.router)
app.include_router(chat.router)
app.include_router(ask.router)
app.include_router(intent.router)

FRONTEND_ROOT = Path(__file__).resolve().parent / "frontends"
USER_FRONTEND_ROOT = FRONTEND_ROOT / "user"
SHARED_FRONTEND_ROOT = FRONTEND_ROOT / "shared"
app.mount(
    "/assets",
    StaticFiles(directory=USER_FRONTEND_ROOT / "assets"),
    name="user-assets",
)
app.mount(
    "/images",
    StaticFiles(directory=SHARED_FRONTEND_ROOT / "images"),
    name="shared-images",
)


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    """HEAPY 사용자 웹 앱을 반환한다.

    작성자: 김진우
    """
    return FileResponse(USER_FRONTEND_ROOT / "index.html")

# 실행 명령어: uvicorn app.main:app --reload
