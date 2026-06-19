from __future__ import annotations

from backend.cloud_api.cloud.event_repository import CloudEventRepository
from backend.cloud_api.cloud.schema import initialize_database
from backend.shared.core.state import RuntimeState


def hydrate_runtime_state(state: RuntimeState, repository: CloudEventRepository, limit: int = 200) -> None:
    if not repository.enabled:
        return
    state.replace_history(
        events=repository.list_events(limit),
        analysis_results=repository.list_analysis_results(limit),
    )
