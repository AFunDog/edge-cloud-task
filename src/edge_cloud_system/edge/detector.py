from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from edge_cloud_system.domain.models import BoundingBox, Detection, DetectionResult

CLASS_NAMES = ["others", "car", "van", "bus"]


class YoloDetector:
    def __init__(
        self,
        model_path: str = "",
        public_dir: str | Path = "public",
        imgsz: int = 640,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.7,
    ) -> None:
        self.public_dir = Path(public_dir)
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self._model_path = self._resolve_model_path(model_path)
        self._backend = ""
        self._onnx_session: Any | None = None
        self._onnx_input_name = ""
        self._onnx_output_names: list[str] = []
        self._openvino_model: Any | None = None
        self._openvino_outputs: list[Any] = []
        self._load_backend()

    @property
    def mode(self) -> str:
        return self._backend

    @property
    def model_path(self) -> str:
        return str(self._model_path)

    def _resolve_model_path(self, model_path: str) -> Path:
        if model_path:
            explicit = Path(model_path)
            if explicit.exists():
                return explicit
            sibling_onnx = explicit.with_suffix(".onnx")
            if sibling_onnx.exists():
                return sibling_onnx
            raise FileNotFoundError(f"YOLO 模型不存在：{explicit}")

        candidates: list[Path] = []
        if self.public_dir.exists():
            for pattern in ("*.onnx", "*.xml", "*.pt"):
                candidates.extend(sorted(self.public_dir.rglob(pattern)))
        if not candidates:
            raise FileNotFoundError("根目录 public/ 下未找到 YOLO 模型文件，请放入 .onnx、.xml 或 .pt 文件。")
        return candidates[0]

    def _load_backend(self) -> None:
        suffix = self._model_path.suffix.lower()
        if suffix == ".pt":
            self._model_path = self._export_pt_to_onnx(self._model_path)
            suffix = self._model_path.suffix.lower()

        if suffix == ".onnx":
            self._load_onnxruntime(self._model_path)
            return

        if suffix == ".xml":
            self._load_openvino(self._model_path)
            return

        raise RuntimeError(f"不支持的 YOLO 模型格式：{self._model_path}")

    def _export_pt_to_onnx(self, pt_path: Path) -> Path:
        onnx_path = pt_path.with_suffix(".onnx")
        if onnx_path.exists():
            return onnx_path

        try:
            from ultralytics import YOLO
        except Exception as exc:
            raise RuntimeError(f"需要 ultralytics 才能把 .pt 导出为 ONNX：{exc}") from exc

        model = YOLO(str(pt_path))
        exported = model.export(format="onnx", imgsz=self.imgsz, dynamic=True, simplify=True, verbose=False)
        exported_path = Path(str(exported))
        if exported_path.exists():
            return exported_path
        if onnx_path.exists():
            return onnx_path
        raise RuntimeError(f".pt 导出 ONNX 后未找到输出文件：{pt_path}")

    def _load_onnxruntime(self, onnx_path: Path) -> None:
        try:
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError(f"ONNX Runtime 未安装，无法加载 {onnx_path}：{exc}") from exc

        providers = [provider for provider in ("CUDAExecutionProvider", "CPUExecutionProvider") if provider in ort.get_available_providers()]
        if not providers:
            providers = ["CPUExecutionProvider"]
        session = ort.InferenceSession(str(onnx_path), providers=providers)
        self._onnx_session = session
        self._onnx_input_name = session.get_inputs()[0].name
        self._onnx_output_names = [item.name for item in session.get_outputs()]
        self._backend = "onnxruntime"

    def _load_openvino(self, xml_path: Path) -> None:
        try:
            import openvino as ov
        except Exception as exc:
            raise RuntimeError(f"OpenVINO 未安装，无法加载 {xml_path}：{exc}") from exc

        core = ov.Core()
        model = core.read_model(str(xml_path))
        model.reshape({model.input().any_name: (1, 3, self.imgsz, self.imgsz)})
        compiled_model = core.compile_model(
            model,
            "CPU",
            {"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "1", "AFFINITY": "CORE"},
        )
        self._openvino_model = compiled_model
        self._openvino_outputs = list(compiled_model.outputs)
        self._backend = "openvino"

    def detect(self, device_id: str, frame: Any | None = None, image_jpeg_base64: str | None = None) -> DetectionResult:
        if frame is None:
            raise RuntimeError("未读取到摄像头帧，无法执行边端 YOLO 检测。")

        start = time.perf_counter()
        boxes, confidences, class_ids = self.process_frame(frame)
        elapsed = max(time.perf_counter() - start, 1e-6)
        width, height = self._frame_size(frame)
        detections = [
            Detection(
                label=self.get_class_name(class_id),
                confidence=float(confidence),
                box=BoundingBox(x1=float(box[0]), y1=float(box[1]), x2=float(box[2]), y2=float(box[3])),
            )
            for box, confidence, class_id in zip(boxes, confidences, class_ids)
        ]
        return DetectionResult(
            device_id=device_id,
            fps=round(1 / elapsed, 2),
            inference_ms=round(elapsed * 1000, 2),
            backend=self._backend,
            model_path=str(self._model_path),
            frame_width=width,
            frame_height=height,
            image_jpeg_base64=image_jpeg_base64,
            detections=detections,
        )

    def process_frame(self, frame: Any) -> tuple[list[list[float]], list[float], list[int]]:
        orig_h, orig_w = frame.shape[:2]
        img_input = self._preprocess_frame(frame)
        outputs = self._run_detector(img_input)

        all_boxes: list[list[float]] = []
        all_confidences: list[float] = []
        all_class_ids: list[int] = []
        for out_data in outputs:
            boxes, confidences, class_ids = self._decode_output(out_data, self.imgsz, self.imgsz)
            all_boxes.extend(boxes)
            all_confidences.extend(confidences)
            all_class_ids.extend(class_ids)

        if not all_boxes:
            return [], [], []

        indices = self._nms(np.array(all_boxes), np.array(all_confidences))
        scale_x = orig_w / self.imgsz
        scale_y = orig_h / self.imgsz
        final_boxes: list[list[float]] = []
        final_confidences: list[float] = []
        final_class_ids: list[int] = []
        for index in indices:
            x1, y1, x2, y2 = all_boxes[int(index)]
            final_boxes.append([x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y])
            final_confidences.append(all_confidences[int(index)])
            final_class_ids.append(all_class_ids[int(index)])
        return final_boxes, final_confidences, final_class_ids

    def _preprocess_frame(self, frame: Any) -> np.ndarray:
        import cv2

        image = cv2.resize(frame, (self.imgsz, self.imgsz))
        if self._backend == "onnxruntime":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = image.astype(np.float32) / 255.0
        image = np.transpose(image, (2, 0, 1))
        return np.expand_dims(image, axis=0)

    def _run_detector(self, img_input: np.ndarray) -> list[np.ndarray]:
        if self._backend == "onnxruntime":
            if self._onnx_session is None:
                raise RuntimeError("ONNX Runtime session 未初始化。")
            return self._onnx_session.run(self._onnx_output_names, {self._onnx_input_name: img_input})

        if self._backend == "openvino":
            if self._openvino_model is None:
                raise RuntimeError("OpenVINO compiled model 未初始化。")
            results = self._openvino_model([img_input])
            return [results[output] for output in self._openvino_outputs]

        raise RuntimeError(f"未知 YOLO 后端：{self._backend}")

    def _decode_output(self, output: Any, img_width: int, img_height: int) -> tuple[list[list[float]], list[float], list[int]]:
        output_array = np.asarray(output)
        if output_array.ndim == 2:
            output_array = np.expand_dims(output_array, axis=0)

        boxes: list[list[float]] = []
        confidences: list[float] = []
        class_ids: list[int] = []
        for pred in output_array[0]:
            if pred.shape[0] < 6:
                continue
            x1, y1, x2, y2 = [float(value) for value in pred[:4]]
            confidence = float(pred[4])
            class_id = int(pred[5])
            if confidence <= self.conf_threshold:
                continue

            x1 = float(np.clip(x1, 0, img_width))
            y1 = float(np.clip(y1, 0, img_height))
            x2 = float(np.clip(x2, 0, img_width))
            y2 = float(np.clip(y2, 0, img_height))
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            boxes.append([x1, y1, x2, y2])
            confidences.append(confidence)
            class_ids.append(class_id)
        return boxes, confidences, class_ids

    def _nms(self, boxes: np.ndarray, scores: np.ndarray) -> np.ndarray:
        import cv2

        if len(boxes) == 0:
            return np.array([], dtype=np.int32)
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), self.conf_threshold, self.iou_threshold)
        return np.asarray(indices).flatten() if len(indices) > 0 else np.array([], dtype=np.int32)

    def get_class_name(self, class_id: int) -> str:
        if 0 <= class_id < len(CLASS_NAMES):
            return CLASS_NAMES[class_id]
        return f"class_{class_id}"

    def _frame_size(self, frame: Any | None) -> tuple[int, int]:
        if frame is None:
            return self.imgsz, self.imgsz
        height, width = frame.shape[:2]
        return int(width), int(height)
