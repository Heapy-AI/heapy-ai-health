from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException

from app.routers.auth import AuthenticatedSession, require_current_session
from app.schemas.checkup_report import CheckupReportRequest, CheckupReportResponse
from app.services.checkup_report import CheckupReportService
from app.services.supabase_conversation import SupabaseConversationError
from app.routers.personal_data import personal_data_service


router = APIRouter(prefix="/me/checkup", tags=["checkup-report"])
report_service = CheckupReportService()


@router.post("/report", response_model=CheckupReportResponse)
async def create_checkup_report(
    request: CheckupReportRequest,
    session: AuthenticatedSession = Depends(require_current_session),
) -> CheckupReportResponse:
    started = perf_counter()
    try:
        history_started = perf_counter()
        history = personal_data_service.get_checkup_history(
            session.access_token,
            str(session.user.get("id", "")),
        )
        history_seconds = perf_counter() - history_started

        if len(history) < 2:
            raise HTTPException(
                status_code=400,
                detail="AI 요약분석에는 최소 2회의 건강검진 이력이 필요합니다.",
            )

        report, trace = await report_service.generate_with_trace(history,persona=request.persona)
        total_seconds = perf_counter() - started

        return CheckupReportResponse(
            success=True,
            report=report,
            checkup_count=len(history),
            verification={
                "source": "Supabase health_checkup_records + health_checkup_results",
                "history": history,
                "db_status_used": True,
                "persona": request.persona, # 어떤 페르소나를 사용했는지 확인
                "timings": {
                    "history_seconds": round(history_seconds,3),
                    **trace["timings"],
                    "total_seconds": round(total_seconds, 3),
                },
                "analysis_input": trace["analysis_input"],
            },
        )

    except HTTPException:
        raise

    except SupabaseConversationError as error:
        status_code = error.status_code if error.status_code in {400, 401, 403, 404, 409, 503} else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error

    except Exception as error:
        raise HTTPException(status_code=502, detail="AI 요약분석을 생성하지 못했습니다.") from error
