"""pytest 全局配置 —— 测试结束后清理残余测试数据。"""

import pytest

from backend.shared.core.state import runtime_state

_TEST_MARKERS = {"test_daily", "integration_test"}


@pytest.fixture(autouse=True)
def _cleanup_runtime_state() -> None:
    """每个测试前清理上次运行可能残留的测试事件。"""
    snap = runtime_state.snapshot()
    try:
        runtime_state._events = type(runtime_state._events)(
            [e for e in snap["events"] if e.event_type not in _TEST_MARKERS],
            maxlen=runtime_state._events.maxlen,
        )
    except Exception:
        pass
    try:
        runtime_state._analysis_results = type(runtime_state._analysis_results)(
            [r for r in snap["analysis_results"]
             if not any(e.event_id == r.event_id for e in snap["events"] if e.event_type in _TEST_MARKERS)],
            maxlen=runtime_state._analysis_results.maxlen,
        )
    except Exception:
        pass
