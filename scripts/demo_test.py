"""
端到端集成测试脚本 —— 验证边端→云端→前端全链路功能。

用法:
  python scripts/demo_test.py --help
  python scripts/demo_test.py                     # 运行全部
  python scripts/demo_test.py --quick              # 快速冒烟
  python scripts/demo_test.py --skip-docker        # 跳过 Docker 验证

依赖:
  pytest (可选: 二阶段验证会调用 pytest)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
EDGE_URL = "http://localhost:8001"
CLOUD_URL = "http://localhost:8000"


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}" + (f"  | {detail}" if detail else ""))
    return ok


def test_unit() -> bool:
    section("1. 单元测试")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q", "--tb=short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    detail = f"{result.stdout.splitlines()[-1] if result.stdout.strip() else result.stderr.strip()[:80]}"
    if not ok:
        print(result.stderr[:500])
    return check("pytest 全量", ok, detail)


def test_compile() -> bool:
    section("2. 编译检查")
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(ROOT / "src" / "backend")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    return check("compileall src/backend", ok, result.stderr.strip()[:120] if result.stderr else "")


def test_cloud_api() -> bool:
    section("3. 云端 API")
    ok = True
    try:
        r = httpx.get(f"{CLOUD_URL}/health", timeout=5)
        ok &= check("GET /health", r.status_code == 200, f"status={r.status_code}")
        r = httpx.get(f"{CLOUD_URL}/api/state", timeout=5)
        data = r.json()
        ok &= check("GET /api/state", r.status_code == 200, f"keys={list(data.keys())}")
        ok &= check("state has events", "events" in data, "")
        ok &= check("state has analysis_results", "analysis_results" in data, "")
    except httpx.RequestError as exc:
        ok = False
        check("Cloud API 连接", False, f"无法连接: {exc}")
    return ok


def test_cloud_events_api() -> bool:
    section("3.1 云端事件 API")
    ok = True
    try:
        from backend.shared.domain.models import EventSeverity, EventStatus, SafetyEvent
        event = SafetyEvent(
            event_type="integration_test",
            device_id="test-runner",
            severity=EventSeverity.INFO,
            status=EventStatus.EDGE_RESOLVED,
            summary="集成测试事件",
        )
        payload = event.model_dump(mode="json")
        r = httpx.post(f"{CLOUD_URL}/api/events", json=payload, timeout=5)
        ok &= check("POST /api/events", r.status_code == 200, f"event_id={r.json().get('event_id','?')}")

        r = httpx.post(
            f"{CLOUD_URL}/api/events/analyze",
            json={"event": payload},
            timeout=10,
        )
        ok &= check("POST /api/events/analyze", r.status_code == 200, f"risk={r.json().get('risk_level','?')}")

        r = httpx.get(f"{CLOUD_URL}/api/events/{event.event_id}/report", timeout=5)
        ok &= check("GET /api/events/:id/report", r.status_code == 200, "markdown report")

        r = httpx.get(f"{CLOUD_URL}/api/events/search?q=integration_test", timeout=5)
        ok &= check("GET /api/events/search", r.status_code == 200, "")
    except httpx.RequestError as exc:
        ok = False
        check("Cloud Events API", False, str(exc))
    except ImportError:
        check("Cloud Events API (model import)", False, "无法导入模型")
        ok = False
    return ok


def test_cloud_agent_api() -> bool:
    section("3.2 云端 Agent API")
    ok = True
    try:
        r = httpx.post(
            f"{CLOUD_URL}/api/agent/chat",
            json={"question": "系统自检，请回答 ok。", "device_id": "test-runner", "context": {}},
            timeout=10,
        )
        ok &= check("POST /api/agent/chat", r.status_code == 200, f"traces={len(r.json().get('traces',[]))}")

        r = httpx.get(f"{CLOUD_URL}/api/agent/scan?hours=24", timeout=10)
        data = r.json()
        ok &= check("GET /api/agent/scan", r.status_code == 200, f"hazards={len(data.get('hazards',[]))}")

        r = httpx.get(f"{CLOUD_URL}/api/agent/tools", timeout=5)
        data = r.json()
        has_scan = "hazard_scan" in data
        ok &= check("GET /api/agent/tools", has_scan, f"tools={list(data.keys())}")

        r = httpx.get(f"{CLOUD_URL}/api/reports/daily", timeout=10)
        data = r.json()
        has_fields = "date" in data and "total" in data and "by_severity" in data
        ok &= check("GET /api/reports/daily", r.status_code == 200 and has_fields, f"total={data.get('total',0)}")

    except httpx.RequestError as exc:
        ok = False
        check("Cloud Agent API", False, str(exc))
    return ok


def test_log_query() -> bool:
    section("3.3 日志查询工具")
    try:
        from backend.cloud_api.cloud.log_query import LogQueryTool
        tool = LogQueryTool()
        summary = tool.summarize(hours_back=168)
        ok1 = check("summarize(total)", sum(summary.get("by_type", {}).values()) >= 0, f"total={summary['total']}")
        hazards = tool.scan_hazards(hours_back=168)
        ok2 = check("scan_hazards", isinstance(hazards, list), f"count={len(hazards)}")
        return ok1 and ok2
    except ImportError as exc:
        check("LogQueryTool 导入", False, str(exc))
        return False


def test_knowledge_base() -> bool:
    section("3.4 知识库")
    try:
        from backend.cloud_api.cloud.knowledge import KnowledgeBase
        kb = KnowledgeBase(root=ROOT / "data" / "knowledge")
        hits = kb.search("机房 实验室 时段")
        ok = check("知识库检索", len(hits) > 0, f"hits={len(hits)}")
        for hit in hits[:2]:
            print(f"    -> {hit[:80]}...")
        return ok
    except ImportError as exc:
        check("KnowledgeBase 导入", False, str(exc))
        return False


def test_frontend_build() -> bool:
    section("4. 前端构建")
    ok = True
    for name in ["cloud_frontend", "edge_frontend"]:
        frontend_dir = ROOT / "src" / "frontend" / name
        if not (frontend_dir / "node_modules").exists():
            check(f"{name} (node_modules)", False, "未安装依赖，跳过构建")
            ok = False
            continue
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
        )
        ok &= check(f"{name} build", result.returncode == 0, "")
        if result.returncode != 0:
            print(result.stderr[-300:] if result.stderr else "")
    return ok


def test_docker_config() -> bool:
    section("5. Docker 配置")
    compose_file = ROOT / "docker-compose.yml"
    ok = check("docker-compose.yml 存在", compose_file.exists(), str(compose_file))

    dockerfiles = [
        ROOT / "Dockerfile.cloud",
        ROOT / "Dockerfile.edge",
    ]
    for df in dockerfiles:
        ok &= check(f"{df.name}", df.exists(), str(df))

    frontend_dockerfiles = [
        ROOT / "src" / "frontend" / "cloud_frontend" / "Dockerfile",
        ROOT / "src" / "frontend" / "edge_frontend" / "Dockerfile",
    ]
    for df in frontend_dockerfiles:
        ok &= check(f"{df.parent.name}/{df.name}", df.exists(), str(df))

    env_example = ROOT / ".env.example"
    ok &= check(".env.example", env_example.exists(), "")
    return ok


def test_env_config() -> bool:
    section("6. 环境配置")
    try:
        from backend.shared.core.config import get_settings
        settings = get_settings()
        ok = True
        ok &= check("model_path", bool(settings.yolo_model_path), str(settings.yolo_model_path)[:50])
        ok &= check("edge_url", bool(settings.edge_api_base_url), settings.edge_api_base_url)
        ok &= check("cloud_url", bool(settings.cloud_api_base_url), settings.cloud_api_base_url)
        ok &= check("allowed_hours", bool(settings.room_allowed_hours_start), f"{settings.room_allowed_hours_start}-{settings.room_allowed_hours_end}")
        ok &= check("room_capacity", settings.room_capacity > 0, str(settings.room_capacity))
    except ImportError as exc:
        check("Settings 导入", False, str(exc))
        ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="边云协同系统集成测试")
    parser.add_argument("--quick", action="store_true", help="仅运行单元测试和编译检查")
    parser.add_argument("--skip-docker", action="store_true", help="跳过 Docker 配置检查")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    args = parser.parse_args()

    results: list[bool] = [test_unit(), test_compile()]

    if not args.quick:
        results.extend([
            test_env_config(),
            test_knowledge_base(),
            test_log_query(),
            test_cloud_api(),
            test_cloud_events_api(),
            test_cloud_agent_api(),
        ])
        if not args.skip_frontend:
            results.append(test_frontend_build())
        if not args.skip_docker:
            results.append(test_docker_config())

    score = sum(results)
    total = len(results)
    section(f"结果: {score}/{total} 通过")
    return 0 if score == total else 1


if __name__ == "__main__":
    sys.exit(main())
