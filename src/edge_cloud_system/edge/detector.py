from __future__ import annotations

import random
import time
from typing import Any

from edge_cloud_system.domain.models import BoundingBox, Detection, DetectionResult


class YoloDetector:
    def __init__(self, model_path: str = "") -> None:
        self.model_path = model_path
        self._model: Any | None = None
        self._load_error: str | None = None
        if model_path:
            self._try_load_model(model_path)

    @property
    def mode(self) -> str:
        return "ultralytics" if self._model is not None else "simulation"

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def _try_load_model(self, model_path: str) -> None:
        try:
            from ultralytics import YOLO

            self._model = YOLO(model_path)
        except Exception as exc:  # pragma: no cover - environment dependent
            self._load_error = str(exc)
            self._model = None

    def detect(self, device_id: str, frame: Any | None = None) -> DetectionResult:
        start = time.perf_counter()
        if self._model is not None and frame is not None:
            detections = self._detect_with_model(frame)
        else:
            detections = self._simulate_detections()
        elapsed = max(time.perf_counter() - start, 1e-6)
        return DetectionResult(device_id=device_id, fps=round(1 / elapsed, 2), detections=detections)

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

    def _simulate_detections(self) -> list[Detection]:
        labels = ["person", "car", "bicycle", "truck"]
        count = random.randint(1, 4)
        detections: list[Detection] = []
        for index in range(count):
            left = 24 + index * 78
            top = 36 + index * 34
            detections.append(
                Detection(
                    label=labels[index % len(labels)],
                    confidence=round(random.uniform(0.72, 0.96), 2),
                    box=BoundingBox(x1=left, y1=top, x2=left + 96, y2=top + 74),
                )
            )
        return detections
