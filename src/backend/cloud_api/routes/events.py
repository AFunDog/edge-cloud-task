from fastapi import APIRouter

from backend.cloud_api.dependencies import get_agent
from backend.shared.core.state import runtime_state
from backend.shared.domain.models import CloudAnalysisRequest, CloudAnalysisResponse, SafetyEvent

router = APIRouter(prefix="/api/events", tags=["cloud-events"])


@router.post("", response_model=SafetyEvent)
def create_event(event: SafetyEvent) -> SafetyEvent:
    runtime_state.add_event(event)
    return event


@router.get("", response_model=list[SafetyEvent])
def list_events() -> list[SafetyEvent]:
    return runtime_state.snapshot()["events"]


@router.post("/analyze", response_model=CloudAnalysisResponse)
def analyze_event(request: CloudAnalysisRequest) -> CloudAnalysisResponse:
    runtime_state.add_event(request.event)
    response = get_agent().analyze_event(request)
    runtime_state.add_analysis_result(response)
    return response


@router.get("/analysis", response_model=list[CloudAnalysisResponse])
def list_analysis_results() -> list[CloudAnalysisResponse]:
    return runtime_state.snapshot()["analysis_results"]
