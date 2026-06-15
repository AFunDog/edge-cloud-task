from backend.shared.domain.models import EdgeStatus


def collect_edge_status(device_id: str, fps: float, network: str = "Wi-Fi") -> EdgeStatus:
    try:
        import psutil

        cpu_percent = float(psutil.cpu_percent(interval=None))
        memory_percent = float(psutil.virtual_memory().percent)
    except Exception:
        cpu_percent = 0.0
        memory_percent = 0.0

    return EdgeStatus(
        device_id=device_id,
        network=network,
        fps=round(fps, 1),
        cpu_percent=round(cpu_percent, 1),
        memory_percent=round(memory_percent, 1),
    )
