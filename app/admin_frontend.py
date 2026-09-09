"""HEAPY 개발자 모니터링 UI 프록시 서버.

작성자: 김진우
수정: 고수연
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas.health_chatbot import ChatRequest


API_BASE_URL = os.getenv("HEAPY_API_BASE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_ROOT = Path(__file__).resolve().parent / "frontends"
ADMIN_FRONTEND_ROOT = FRONTEND_ROOT / "admin"
SHARED_FRONTEND_ROOT = FRONTEND_ROOT / "shared"

app = FastAPI(
    title="HEAPY 개발자 모니터링 UI",
    version="1.0",
    docs_url=None,
    redoc_url=None,
)
app.mount(
    "/assets",
    StaticFiles(directory=ADMIN_FRONTEND_ROOT / "assets"),
    name="admin-assets",
)
app.mount(
    "/images",
    StaticFiles(directory=SHARED_FRONTEND_ROOT / "images"),
    name="shared-images",
)


@app.get("/", include_in_schema=False)
def admin_web_app() -> FileResponse:
    """개발자 모니터링 화면을 반환한다.

    작성자: 김진우
    """
    return FileResponse(ADMIN_FRONTEND_ROOT / "index.html")


def _stream_backend(response: requests.Response) -> Iterator[bytes]:
    """백엔드 SSE 응답을 버퍼링하지 않고 브라우저로 전달한다.

    작성자: 김진우
    """
    try:
        yield from response.iter_content(chunk_size=None)
    finally:
        response.close()


def _request_headers(request: Request, *, accept: str = "application/json") -> dict[str, str]:
    """브라우저 인증 쿠키를 백엔드 요청에 전달한다.

    작성자: 김진우
    """
    headers = {"Accept": accept}
    if cookie := request.headers.get("cookie"):
        headers["Cookie"] = cookie
    return headers


def _proxy_json_response(response: requests.Response) -> Response:
    """백엔드 본문과 인증 쿠키를 브라우저 응답으로 복사한다."""
    proxied = Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json").split(
            ";", maxsplit=1
        )[0],
    )
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    cookies = raw_headers.getlist("Set-Cookie") if raw_headers else []
    for cookie in cookies:
        proxied.headers.append("set-cookie", cookie)
    response.close()
    return proxied


def _proxy_json_request(
    method: str,
    path: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    timeout: tuple[float, float] = (5, 20),
) -> Response:
    """개발자 UI의 JSON API 요청을 메인 API로 중계한다."""
    # 검진 회차·생활 데이터 조회 기간처럼 화면이 붙인 조회 조건을 그대로 넘긴다.
    query = f"?{request.url.query}" if request.url.query else ""
    try:
        backend_response = requests.request(
            method,
            f"{API_BASE_URL}{path}{query}",
            json=payload,
            headers=_request_headers(request),
            timeout=timeout,
        )
    except requests.RequestException:
        return Response(
            content='{"detail":"인증 서버에 연결할 수 없습니다."}',
            status_code=503,
            media_type="application/json",
        )
    return _proxy_json_response(backend_response)


@app.post("/auth/signup", include_in_schema=False)
def proxy_signup(payload: dict[str, Any], request: Request) -> Response:
    """회원가입 요청과 발급 쿠키를 중계한다."""
    return _proxy_json_request("POST", "/auth/signup", request, payload)


@app.post("/auth/login", include_in_schema=False)
def proxy_login(payload: dict[str, Any], request: Request) -> Response:
    """로그인 요청과 발급 쿠키를 중계한다."""
    return _proxy_json_request("POST", "/auth/login", request, payload)


@app.get("/auth/me", include_in_schema=False)
def proxy_me(request: Request) -> Response:
    """현재 사용자 조회 요청을 중계한다."""
    return _proxy_json_request("GET", "/auth/me", request)


@app.post("/auth/refresh", include_in_schema=False)
def proxy_refresh(request: Request) -> Response:
    """인증 세션 갱신과 교체 쿠키를 중계한다."""
    return _proxy_json_request("POST", "/auth/refresh", request)


@app.post("/auth/logout", include_in_schema=False)
def proxy_logout(request: Request) -> Response:
    """로그아웃과 인증 쿠키 제거를 중계한다."""
    return _proxy_json_request("POST", "/auth/logout", request)


@app.get("/health", include_in_schema=False)
def proxy_health(request: Request) -> Response:
    """개발자 UI의 백엔드 상태 조회를 중계한다."""
    return _proxy_json_request("GET", "/health", request)


@app.get("/conversations", include_in_schema=False)
def proxy_conversation_list(request: Request) -> Response:
    """현재 사용자의 대화 세션 목록을 중계한다."""
    return _proxy_json_request("GET", "/conversations", request)


@app.post("/conversations", include_in_schema=False)
def proxy_conversation_create(request: Request) -> Response:
    """새 대화 세션 생성을 중계한다."""
    return _proxy_json_request("POST", "/conversations", request)


@app.get("/conversations/{session_id}", include_in_schema=False)
def proxy_conversation_detail(session_id: str, request: Request) -> Response:
    """선택한 대화 세션과 메시지 조회를 중계한다."""
    return _proxy_json_request("GET", f"/conversations/{session_id}", request)


@app.delete("/conversations/{session_id}", include_in_schema=False)
def proxy_conversation_delete(session_id: str, request: Request) -> Response:
    """선택한 대화 세션 삭제를 중계한다."""
    return _proxy_json_request("DELETE", f"/conversations/{session_id}", request)


@app.get("/me/checkup", include_in_schema=False)
def proxy_latest_checkup(request: Request) -> Response:
    """현재 사용자의 최신 검진 1회 조회를 중계한다.

    작성자: 고수연
    """
    return _proxy_json_request("GET", "/me/checkup", request)


@app.post("/me/checkup/report", include_in_schema=False)
def proxy_checkup_report(request: Request) -> Response:
    """건강검진 전체 이력 AI 요약분석 요청을 중계한다."""
    return _proxy_json_request(
        "POST",
        "/me/checkup/report",
        request,
        timeout=(5, 180),
    )


@app.get("/me/checkup/records", include_in_schema=False)
def proxy_checkup_records(request: Request) -> Response:
    """건강검진 회차 목록을 메인 API로 중계한다."""
    return _proxy_json_request("GET", "/me/checkup/records", request)


@app.get("/me/lifestyle", include_in_schema=False)
def proxy_lifestyle_window(request: Request) -> Response:
    """현재 사용자의 최신 1주일치 생활 데이터 조회를 중계한다.

    작성자: 고수연
    """
    return _proxy_json_request("GET", "/me/lifestyle", request)


@app.post("/me/lifestyle/report", include_in_schema=False)
def proxy_lifestyle_report(request: Request) -> Response:
    """생활건강 탭별 AI 분석 요청을 중계한다.

    작성자: 고수연
    """
    return _proxy_json_request(
        "POST",
        "/me/lifestyle/report",
        request,
        timeout=(5, 180),
    )


@app.post("/chat/stream", include_in_schema=False)
def proxy_chat_stream(payload: ChatRequest, request: Request) -> Response:
    """개발자 UI 질문을 메인 FastAPI 스트리밍 API로 중계한다.

    작성자: 김진우
    """
    try:
        backend_response = requests.post(
            f"{API_BASE_URL}/chat/stream",
            json=payload.model_dump(),
            headers=_request_headers(request, accept="text/event-stream"),
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
