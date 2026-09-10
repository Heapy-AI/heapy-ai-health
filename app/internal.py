"""Spring Boot 전용 챗봇 진입점. 작성자: 김진우."""

import hmac
import json
import os
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.state import state
from app.health_analysis import build_router


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class InternalChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contractVersion: Literal["1.0"]
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    summary: str = Field(default="", max_length=4000)
    persona: Literal["coach", "professional"] = "coach"
    personalContext: str = Field(default="", max_length=20000)

    @field_validator("message")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("질문을 입력해 주세요.")
        return value.strip()


def authorize(authorization: str = Header(default="")) -> None:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "내부 인증 설정이 준비되지 않았습니다.")
    if not hmac.compare_digest(authorization.encode(), ("Bearer " + expected).encode()):
        raise HTTPException(401, "내부 인증이 필요합니다.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(os.environ.get("INTERNAL_SERVICE_TOKEN", "")) < 32:
        raise RuntimeError("내부 서비스 인증 설정이 필요합니다.")
    from app.core.runtime import lifespan as initialize
    async with initialize(app):
        yield


app = FastAPI(title="HEAPY 내부 챗봇", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

# 작성자: 김진우 — 데모 인증 경로를 공개하지 않고 건강 분석만 등록한다.
app.include_router(build_router(authorize))


@app.middleware("http")
async def limit_body(request, call_next):
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 262144:
            return JSONResponse(status_code=413, content={"code": "PAYLOAD_TOO_LARGE"})
        chunks.append(chunk)
    request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    # 작성자: 김진우 — 검증 오류에 입력된 건강 문맥과 질문을 복제하지 않는다.
    return JSONResponse(status_code=422, content={"code": "INVALID_INPUT"})


@app.get("/health/ready")
def ready():
    if not state.get("ready") or not state.get("chat_orchestrator"):
        raise HTTPException(503, "모델을 준비 중입니다.")
    return {"status": "ready", "contractVersion": "1.0"}


@app.post("/internal/chat/answer", dependencies=[Depends(authorize)])
def answer(request: InternalChatRequest):
    orchestrator = state.get("chat_orchestrator")
    if not orchestrator:
        raise HTTPException(503, "챗봇이 준비되지 않았습니다.")
    try:
        result = orchestrator.answer(
            request.message, history=[turn.model_dump() for turn in request.history],
            summary=request.summary, persona=request.persona,
            personal_context_loader=lambda question, terms: request.personalContext or None,
        )
        return result_response(result)
    except Exception:
        # 작성자: 김진우 — 공급자 예외의 요청 본문·키를 응답이나 로그에 남기지 않는다.
        raise HTTPException(503, "챗봇 응답을 완료하지 못했습니다.") from None


def result_diagnostics(result):
    """데모 결과 중 본문 없는 진단 정보만 선별한다. 작성자: 김진우."""
    values = {}
    for target, source in {"intent": "intent", "modelVersion": "model_version",
                           "verificationMethod": "verification_method", "evidenceStatus": "evidence_status",
                           "auditStatus": "audit_status"}.items():
        value = getattr(result, source, "")
        value = getattr(value, "value", value)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value):
            values[target] = value
    for target, source in {"personalContextUsed": "personal_context_used", "grounded": "grounded",
                           "uncertain": "uncertain", "guardTriggered": "guard_triggered", "emergency": "emergency"}.items():
        value = getattr(result, source, None)
        if isinstance(value, bool):
            values[target] = value
    confidence = getattr(result, "confidence", None)
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= confidence <= 1:
        values["confidence"] = confidence
    for target, source in {"documentCount": "documents", "citationCount": "cited_chunk_ids",
                           "failedCollectionCount": "failed_collections", "searchedCollectionCount": "searched_collections"}.items():
        values[target] = min(len(getattr(result, source, []) or []), 10000)
    return values


def result_response(result):
    citations = []
    if result.grounded:
        for key in result.cited_chunk_ids:
            if not key.startswith("C") or not key[1:].isdigit():
                continue
            index = int(key[1:]) - 1
            if 0 <= index < len(result.documents):
                metadata = result.documents[index].metadata
                document_id = str(metadata.get("record_id", ""))[:200]
                url = str(metadata.get("source_url", metadata.get("url", "")))[:2000]
                if not url.startswith("https://"):
                    url = ""
                if document_id or url:
                    citations.append({"title": str(metadata.get("title", metadata.get("source", "건강정보 근거")))[:300],
                                      "documentId": document_id or None, "sourceUrl": url or None})
    if not result.answer.strip() or len(result.answer) > 16000:
        raise ValueError("응답 형식 오류")
    return {"answer": result.answer, "citations": citations[:12],
            "summary": result.conversation_summary[:4000],
            "diagnostics": result_diagnostics(result),
            "metadata": {"intent": result.intent.value, "emergency": result.emergency,
                             "personalContextUsed": result.personal_context_used}}


def event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


@app.post("/internal/chat/stream", dependencies=[Depends(authorize)])
def stream(request: InternalChatRequest, x_request_id: str = Header(default="")):
    orchestrator = state.get("chat_orchestrator")
    if not orchestrator:
        raise HTTPException(503, "챗봇이 준비되지 않았습니다.")

    def generate():
        total = 0
        stage = "prepare_query"
        started = time.monotonic()
        try:
            trace_id = str(uuid.UUID(x_request_id))
        except ValueError:
            trace_id = str(uuid.uuid4())
        logger = logging.getLogger("heapy.chat.diagnostics")
        allowed_stages = {"prepare_query", "classify_intent", "load_health_context", "search_evidence",
                          "generate_answer", "verify_answer", "summarize_conversation"}
        try:
            for item in orchestrator.stream_answer(
                request.message, history=[turn.model_dump() for turn in request.history],
                summary=request.summary, persona=request.persona,
                personal_context_loader=lambda question, terms: request.personalContext or None,
            ):
                if item.event == "progress":
                    if item.stage in allowed_stages:
                        stage = item.stage
                    yield event("status", {"stage": stage})
                elif item.event == "token":
                    total += len(item.text)
                    if total > 16000:
                        raise ValueError("응답 한도 초과")
                    yield event("delta", {"content": item.text})
                elif item.event == "complete" and item.result is not None:
                    yield event("done", result_response(item.result))
                    logger.warning("chat_diagnostic requestId=%s status=completed stage=%s elapsedMs=%d", trace_id, stage, int((time.monotonic()-started)*1000))
                    return
            logger.warning("chat_diagnostic requestId=%s status=failed stage=%s errorCode=incomplete_stream", trace_id, stage)
            yield event("error", {"code": "CHAT_UNAVAILABLE", "stage": stage, "diagnosticCode": "incomplete_stream"})
        except Exception as error:
            code = "timeout" if isinstance(error, TimeoutError) else "invalid_response" if isinstance(error, ValueError) else "upstream_failure"
            logger.warning("chat_diagnostic requestId=%s status=failed stage=%s errorCode=%s elapsedMs=%d", trace_id, stage, code, int((time.monotonic()-started)*1000))
            yield event("error", {"code": "CHAT_UNAVAILABLE", "stage": stage, "diagnosticCode": code})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
