from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from edge_cloud_system.domain.models import BoundingBox, Detection, DetectionResult


class YoloDetector:
    def __init__(self, model_path: str = "", public_dir: str | Path = "public") -> None:
        self.model_path = str(self._resolve_model_path(model_path, Path(public_dir)))
        self._model: Any | None = None
        self._load_error: str | None = None
        if self.model_path:
            self._try_load_model(self.model_path)

    @property
    def mode(self) -> str:
        return "ultralytics"

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def _try_load_model(self, model_path: str) -> None:
        try:
            from ultralytics import YOLO

            self._model = YOLO(model_path)
        except Exception as exc:  # pragma: no cover - environment dependent
            self._load_error = str(exc)
            raise RuntimeError(f"YOLO 模型加载失败：{exc}") from exc

    def _resolve_model_path(self, model_path: str, public_dir: Path) -> Path | str:
        if model_path:
            return model_path
        candidates: list[Path] = []
        if public_dir.exists():
            for pattern in ("*.pt", "*.onnx", "*.engine"):
                candidates.extend(sorted(public_dir.rglob(pattern)))
        if not candidates:
            raise FileNotFoundError("根目录 public/ 下未找到 YOLO 模型文件，请放入 .pt、.onnx 或 .engine 文件。")
        return candidates[0]

    def detect(self, device_id: str, frame: Any | None = None, image_jpeg_base64: str | None = None) -> DetectionResult:
        if frame is None:
            raise RuntimeError("未读取到摄像头帧，无法执行边端 YOLO 检测。")
        if self._model is None:
            raise RuntimeError("YOLO 模型未加载，无法执行边端检测。")

        start = time.perf_counter()
        detections = self._detect_with_model(frame)
        elapsed = max(time.perf_counter() - start, 1e-6)
        width, height = self._frame_size(frame)
        return DetectionResult(
            device_id=device_id,
            fps=round(1 / elapsed, 2),
            frame_width=width,
            frame_height=height,
            image_jpeg_base64=image_jpeg_base64,
            detections=detections,
        )

    def _detect_with_model(self, frame: Any) -> list[Detection]:  # pragma: no cover - requires model
        results = self._model(frame, verbose=False)
        parsed: list[Detection] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                class_id = int(box.cls[0])
                parsed.append(
                    Detection(
                        label=str(names.get(class_id, class_id)),
                        confidence=float(box.conf[0]),
                        box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    )
                )
        return parsed

    def _frame_size(self, frame: Any | None) -> tuple[int, int]:
        if frame is None:
            return 640, 360
        height, width = frame.shape[:2]
        return int(width), int(height)
