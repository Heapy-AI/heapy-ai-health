"""HEAPY 사용자 시연용 웹 UI 서버.

작성자: 김진우
"""

import os
from collections.abc import Iterator
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas.health_chatbot import ChatRequest


API_BASE_URL = os.getenv("HEAPY_API_BASE_URL", "http://localhost:8000").rstrip("/")
DEMO_ROOT = Path(__file__).resolve().parent / "demo_web"
IMAGE_ROOT = Path(__file__).resolve().parent / "web" / "assets" / "images"

app = FastAPI(
    title="HEAPY 사용자 시연 UI",
    version="1.0",
    docs_url=None,
    redoc_url=None,
)
app.mount("/assets", StaticFiles(directory=DEMO_ROOT / "assets"), name="demo-assets")
app.mount("/images", StaticFiles(directory=IMAGE_ROOT), name="demo-images")


@app.get("/", include_in_schema=False)
def demo_web_app() -> FileResponse:
    """사용자 시연용 챗봇 화면을 반환한다.

    작성자: 김진우
    """
    return FileResponse(DEMO_ROOT / "index.html")


def _stream_backend(response: requests.Response) -> Iterator[bytes]:
    """백엔드 SSE 응답을 버퍼링하지 않고 브라우저로 전달한다.

    작성자: 김진우
    """
    try:
        yield from response.iter_content(chunk_size=None)
    finally:
        response.close()


@app.post("/chat/stream", include_in_schema=False)
def proxy_chat_stream(request: ChatRequest) -> Response:
    """사용자 질문을 기존 FastAPI 스트리밍 API로 중계한다.

    작성자: 김진우
    """
    try:
        backend_response = requests.post(
            f"{API_BASE_URL}/chat/stream",
            json=request.model_dump(),
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=(5, 180),
        )
    except requests.RequestException:
        return Response(
            content='{"detail":"건강정보 서버에 연결할 수 없습니다."}',
            status_code=503,
            media_type="application/json",
        )

    if not backend_response.ok:
        content = backend_response.content
        content_type = backend_response.headers.get(
            "content-type",
            "application/json",
        )
        backend_response.close()
        return Response(
            content=content,
            status_code=backend_response.status_code,
            media_type=content_type.split(";", maxsplit=1)[0],
        )

    return StreamingResponse(
        _stream_backend(backend_response),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
