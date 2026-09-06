"""생활건강 탭별 AI 분석 API.

user_id는 세션에서만 꺼내고 조회는 사용자 access token으로 수행하므로 본인 행 격리는
Supabase RLS가 보장한다. 조회 구간은 화면의 기간 버튼과 같은 값을 그대로 받는다.

작성자: 고수연
"""

from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.auth import AuthenticatedSession, require_current_session
from app.routers.personal_data import personal_data_service
from app.schemas.lifestyle_report import LifestyleReportResponse
from app.services.lifestyle_report import DOMAIN_LABELS, LifestyleReportService
from app.services.supabase_conversation import SupabaseConversationError


router = APIRouter(prefix="/me/lifestyle", tags=["lifestyle-report"])
lifestyle_report_service = LifestyleReportService()


@router.post("/report", response_model=LifestyleReportResponse)
async def create_lifestyle_report(
    domain: str = Query(..., pattern="^(bio|activity|nutrition|sleep)$"),
    window_days: int = Query(7, ge=7, le=365),
    session: AuthenticatedSession = Depends(require_current_session),
) -> LifestyleReportResponse:
    """생활건강 탭 하나의 당일 수치와 구간 추세를 AI 설명으로 돌려준다."""
    started = perf_counter()
    try:
        window_started = perf_counter()
        window = personal_data_service.get_lifestyle_window(
            session.access_token,
            str(session.user.get("id", "")),
            window_days,
        )
        window_seconds = perf_counter() - window_started
        analysis = LifestyleReportService.build_analysis(domain, window, window_days)
        if not analysis["metrics"]:
            raise HTTPException(
                status_code=400,
                detail=f"{DOMAIN_LABELS[domain]} 탭에 분석할 기록이 없습니다.",
            )
        report, trace = await lifestyle_report_service.generate_with_trace(
            domain, window, window_days
        )
        return LifestyleReportResponse(
            success=True,
            domain=domain,
            window_days=window_days,
            latest_date=analysis["latest_date"],
            report=report,
            verification={
                "source": "Supabase lifestyle_* tables",
                "timings": {
                    "window_seconds": round(window_seconds, 3),
                    **trace["timings"],
                    "total_seconds": round(perf_counter() - started, 3),
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
        raise HTTPException(status_code=502, detail="AI 분석을 생성하지 못했습니다.") from error
