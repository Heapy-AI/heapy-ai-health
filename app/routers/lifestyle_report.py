"""생활건강 탭별 AI 분석 API.

user_id는 세션에서만 꺼내고 조회는 사용자 access token으로 수행하므로 본인 행 격리는
Supabase RLS가 보장한다.

조회 구간은 클라이언트가 정하지 않는다. 같은 데이터라도 구간을 어떻게 자르느냐에 따라
"오르는 흐름"과 "큰 변화 없음"이 갈리므로, 구간 선택 자체가 분석 내용이기 때문이다.
탭마다 알맞은 구간은 서비스가 정하고(services/lifestyle_report.ANALYSIS_WINDOWS),
화면의 기간 버튼은 그래프 전용으로만 쓴다.

작성자: 고수연
"""

from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.auth import AuthenticatedSession, require_current_session
from app.routers.personal_data import personal_data_service
from app.schemas.lifestyle_report import LifestyleReportResponse
from app.services.lifestyle_report import (
    DOMAIN_LABELS,
    PROMPT_VERSION,
    LifestyleReportService,
    age_from_birth_date,
    analysis_window,
)
from app.services.supabase_conversation import SupabaseConversationError
from app.routers.auth import conversation_service


router = APIRouter(prefix="/me/lifestyle", tags=["lifestyle-report"])
lifestyle_report_service = LifestyleReportService()


@router.post("/report", response_model=LifestyleReportResponse)
async def create_lifestyle_report(
    domain: str = Query(..., pattern="^(bio|activity|nutrition|sleep)$"),
    session: AuthenticatedSession = Depends(require_current_session),
) -> LifestyleReportResponse:
    """생활건강 탭 하나를 전체 흐름과 최근 상태 두 시선으로 분석한다."""
    started = perf_counter()
    windows = analysis_window(domain)
    try:
        window_started = perf_counter()
        # 긴 구간을 한 번만 조회하고, 최근 구간은 그 결과를 날짜로 잘라 만든다.
        window = personal_data_service.get_lifestyle_window(
            session.access_token,
            str(session.user.get("id", "")),
            windows["full"],
        )
        window_seconds = perf_counter() - window_started
        # 영양 기준은 성별과 나이로 갈린다. 프로필을 못 읽으면 모르는 채로 진행한다.
        # 판정이 조금 느슨해질 뿐이고, 어느 잣대로 쟀는지는 화면 각주가 밝힌다.
        try:
            profile = conversation_service.get_profile(
                session.access_token,
                str(session.user.get("id", "")),
            )
        except SupabaseConversationError:
            profile = None
        sex = str((profile or {}).get("sex", "")) or None
        age = age_from_birth_date((profile or {}).get("birth_date"))
        analysis = LifestyleReportService.build_analysis(domain, window, sex, age)
        if not analysis["metrics"]:
            raise HTTPException(
                status_code=400,
                detail=f"{DOMAIN_LABELS[domain]} 탭에 분석할 기록이 없습니다.",
            )
        report, trace = await lifestyle_report_service.generate_with_trace(domain, window, sex, age)
        return LifestyleReportResponse(
            success=True,
            domain=domain,
            window_days=windows["full"],
            recent_days=windows["recent"],
            covered_range=analysis["covered_range"],
            data_truncated=analysis["data_truncated"],
            latest_date=analysis["latest_date"],
            reference_basis=analysis["reference_basis"],
            prompt_version=PROMPT_VERSION,
            report=report,
            verification={
                "source": "Supabase lifestyle_* tables",
                "prompt_version": PROMPT_VERSION,
                "analysis_windows": windows,
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
