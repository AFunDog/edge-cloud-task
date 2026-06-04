from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def api_get(path: str) -> dict[str, Any]:
    response = httpx.get(f"{API_BASE_URL}{path}", timeout=5)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(f"{API_BASE_URL}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def draw_detection_panel(detections: list[dict[str, Any]]) -> None:
    st.subheader("实时检测")
    if not detections:
        st.info("暂无边端检测上报。")
        return

    latest = detections[0]
    st.caption(f"Frame {latest['frame_id']} | FPS {latest['fps']} | {latest['created_at']}")
    canvas = """
    <div class="video-plane">
      <div class="scanline"></div>
    """
    for item in latest["detections"]:
        box = item["box"]
        left = min(box["x1"] / 640 * 100, 86)
        top = min(box["y1"] / 360 * 100, 78)
        width = max((box["x2"] - box["x1"]) / 640 * 100, 8)
        height = max((box["y2"] - box["y1"]) / 360 * 100, 10)
        label = f"{item['label']} {item['confidence']:.2f}"
        canvas += (
            f'<div class="det-box" style="left:{left}%;top:{top}%;width:{width}%;height:{height}%;">'
            f"<span>{label}</span></div>"
        )
    canvas += "</div>"
    st.markdown(canvas, unsafe_allow_html=True)

    rows = [
        {
            "label": item["label"],
            "confidence": item["confidence"],
            "box": f"{item['box']['x1']:.0f},{item['box']['y1']:.0f},{item['box']['x2']:.0f},{item['box']['y2']:.0f}",
        }
        for item in latest["detections"]
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Edge Cloud Console", layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: #101417; color: #e7ecef; }
        [data-testid="stSidebar"] { background: #151b1f; border-right: 1px solid #2e3a40; }
        .metric-card { border: 1px solid #334047; padding: 12px; border-radius: 6px; background: #182024; }
        .video-plane {
            position: relative; height: 340px; border: 1px solid #3d4b52; border-radius: 6px;
            background:
              linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px),
              linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
              #0b1114;
            background-size: 32px 32px;
            overflow: hidden;
        }
        .scanline { position: absolute; inset: 0; background: linear-gradient(180deg, transparent, rgba(77, 214, 171, .18), transparent); height: 90px; animation: scan 4s linear infinite; }
        @keyframes scan { from { transform: translateY(-100px); } to { transform: translateY(360px); } }
        .det-box { position: absolute; border: 2px solid #4dd6ab; box-shadow: 0 0 0 1px rgba(0,0,0,.5); }
        .det-box span { position: absolute; left: -2px; top: -24px; background: #4dd6ab; color: #07100d; font-size: 12px; padding: 2px 6px; border-radius: 3px; white-space: nowrap; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("端-边-云协同管理平台")
    st.caption("边缘检测、任务调度、云端智能体与系统状态总览")

    try:
        state = api_get("/api/state")
        healthy = True
    except Exception as exc:
        state = {"edge_status": [], "recent_detections": [], "task_logs": []}
        healthy = False
        st.error(f"API 连接失败：{exc}")

    with st.sidebar:
        st.header("系统状态")
        st.metric("API", "online" if healthy else "offline")
        st.write(API_BASE_URL)
        if st.button("刷新状态", use_container_width=True):
            st.rerun()

        edge_status = state.get("edge_status", [])
        st.divider()
        st.subheader("边端设备")
        if edge_status:
            for device in edge_status:
                st.markdown(
                    f"""
                    <div class="metric-card">
                      <b>{device['device_id']}</b><br/>
                      网络：{device['network']}<br/>
                      FPS：{device['fps']}<br/>
                      CPU：{device['cpu_percent']}% | MEM：{device['memory_percent']}%
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("暂无设备在线。")

    left, right = st.columns([1.35, 1])
    with left:
        draw_detection_panel(state.get("recent_detections", []))
        st.subheader("任务日志")
        logs = state.get("task_logs", [])
        if logs:
            st.dataframe(logs, use_container_width=True, hide_index=True)
        else:
            st.info("暂无任务日志。")

    with right:
        st.subheader("智能体对话")
        question = st.text_area("问题", value="请分析当前边缘端画面是否存在异常，并给出调度建议。", height=120)
        device_id = st.text_input("设备 ID", value="edge-camera-01")
        if st.button("发送给云端智能体", use_container_width=True):
            try:
                response = api_post(
                    "/api/agent/chat",
                    {"question": question, "device_id": device_id, "context": {"source": "management"}},
                )
                st.success(response["answer"])
                with st.expander("工具调用轨迹", expanded=True):
                    for trace in response["traces"]:
                        st.write(trace)
            except Exception as exc:
                st.error(f"智能体请求失败：{exc}")

        st.subheader("任务调度")
        task = st.text_input("任务描述", value="车辆计数")
        if st.button("预测执行位置", use_container_width=True):
            try:
                decision = api_post("/api/tasks/schedule", {"task": task, "device_id": device_id, "context": {}})
                st.info(f"{decision['target']} / {decision['complexity']}：{decision['reason']}")
            except Exception as exc:
                st.error(f"调度失败：{exc}")


if __name__ == "__main__":
    main()
