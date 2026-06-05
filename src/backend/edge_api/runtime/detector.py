from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Any

import numpy as np

from backend.shared.edge_cloud_system.domain.models import BoundingBox, Detection, DetectionResult, Keypoint

DEFAULT_CLASS_NAMES = ["others", "car", "van", "bus"]
DEFAULT_KEYPOINT_NAMES = [
    "nose","left_eye","right_eye","left_ear","right_ear","left_shoulder","right_shoulder","left_elbow","right_elbow",
    "left_wrist","right_wrist","left_hip","right_hip","left_knee","right_knee","left_ankle","right_ankle",
]


class YoloDetector:
    def __init__(self, model_path: str = "", public_dir: str | Path = "public", imgsz: int = 640, conf_threshold: float = 0.25, iou_threshold: float = 0.7) -> None:
        self.public_dir = Path(public_dir)
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self._model_path = self._resolve_model_path(model_path)
        self._backend = ""
        self._model_task = "detect"
        self._class_names = list(DEFAULT_CLASS_NAMES)
        self._keypoint_names = list(DEFAULT_KEYPOINT_NAMES)
        self._onnx_session: Any | None = None
        self._onnx_input_name = ""
        self._onnx_output_names: list[str] = []
        self._load_backend()

    @property
    def mode(self) -> str: return self._backend
    @property
    def model_path(self) -> str: return str(self._model_path)
    @property
    def task(self) -> str: return self._model_task

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
            candidates.extend(sorted(self.public_dir.rglob("*.onnx")))
        if not candidates:
            raise FileNotFoundError("根目录 public/ 下未找到 YOLO 模型文件，请放入 .onnx 文件。")
        return candidates[0]

    def _load_backend(self) -> None:
        if self._model_path.suffix.lower() == ".onnx":
            self._load_onnxruntime(self._model_path)
            return
        raise RuntimeError(f"不支持的 YOLO 模型格式：{self._model_path}，当前仅支持 .onnx")

    def _load_onnxruntime(self, onnx_path: Path) -> None:
        try:
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError(f"ONNX Runtime 未安装，无法加载 {onnx_path}：{exc}") from exc
        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self._onnx_session = session
        self._onnx_input_name = session.get_inputs()[0].name
        self._onnx_output_names = [item.name for item in session.get_outputs()]
        metadata = session.get_modelmeta().custom_metadata_map
        self._model_task = self._parse_metadata_text(metadata.get("task"), fallback="detect")
        self._class_names = self._parse_names(metadata.get("names"), fallback=self._class_names)
        self._keypoint_names = self._parse_keypoint_names(metadata.get("kpt_names"), fallback=self._keypoint_names)
        self._backend = "onnxruntime"

    def detect(self, device_id: str, frame: Any | None = None, image_jpeg_base64: str | None = None) -> DetectionResult:
        if frame is None:
            raise RuntimeError("未读取到摄像头帧，无法执行边端 YOLO 检测。")
        start = time.perf_counter()
        boxes, confidences, class_ids, keypoints_list = self.process_frame(frame)
        elapsed = max(time.perf_counter() - start, 1e-6)
        width, height = self._frame_size(frame)
        detections = [
            Detection(
                label=self.get_class_name(class_id),
                confidence=float(confidence),
                box=BoundingBox(x1=float(box[0]), y1=float(box[1]), x2=float(box[2]), y2=float(box[3])),
                keypoints=[Keypoint(x=float(kpt_x), y=float(kpt_y), confidence=float(kpt_conf), name=self.get_keypoint_name(index)) for index, (kpt_x, kpt_y, kpt_conf) in enumerate(keypoints)],
            )
            for box, confidence, class_id, keypoints in zip(boxes, confidences, class_ids, keypoints_list)
        ]
        return DetectionResult(device_id=device_id, fps=round(1 / elapsed, 2), inference_ms=round(elapsed * 1000, 2), backend=self._backend, model_path=str(self._model_path), model_task=self._model_task, frame_width=width, frame_height=height, image_jpeg_base64=image_jpeg_base64, detections=detections)

    def process_frame(self, frame: Any) -> tuple[list[list[float]], list[float], list[int], list[list[tuple[float, float, float]]]]:
        import cv2
        orig_h, orig_w = frame.shape[:2]
        img_input = self._preprocess_frame(frame)
        outputs = self._run_detector(img_input)
        all_boxes: list[list[float]] = []
        all_confidences: list[float] = []
        all_class_ids: list[int] = []
        all_keypoints: list[list[tuple[float, float, float]]] = []
        for out_data in outputs:
            boxes, confidences, class_ids, keypoints = self._decode_output(out_data, self.imgsz, self.imgsz)
            all_boxes.extend(boxes); all_confidences.extend(confidences); all_class_ids.extend(class_ids); all_keypoints.extend(keypoints)
        if not all_boxes:
            return [], [], [], []
        indices = cv2.dnn.NMSBoxes(all_boxes, all_confidences, self.conf_threshold, self.iou_threshold)
        indices = np.asarray(indices).flatten() if len(indices) > 0 else np.array([], dtype=np.int32)
        scale_x = orig_w / self.imgsz; scale_y = orig_h / self.imgsz
        final_boxes=[]; final_confidences=[]; final_class_ids=[]; final_keypoints=[]
        for index in indices:
            x1, y1, x2, y2 = all_boxes[int(index)]
            final_boxes.append([x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y])
            final_confidences.append(all_confidences[int(index)])
            final_class_ids.append(all_class_ids[int(index)])
            final_keypoints.append([(float(kpt_x * scale_x), float(kpt_y * scale_y), float(kpt_conf)) for kpt_x, kpt_y, kpt_conf in all_keypoints[int(index)]])
        return final_boxes, final_confidences, final_class_ids, final_keypoints

    def _preprocess_frame(self, frame: Any) -> np.ndarray:
        import cv2
        image = cv2.resize(frame, (self.imgsz, self.imgsz))
        if self._backend == "onnxruntime":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = image.astype(np.float32) / 255.0
        image = np.transpose(image, (2, 0, 1))
        return np.expand_dims(image, axis=0)

    def _run_detector(self, img_input: np.ndarray) -> list[np.ndarray]:
        if self._onnx_session is None:
            raise RuntimeError("ONNX Runtime session 未初始化。")
        return self._onnx_session.run(self._onnx_output_names, {self._onnx_input_name: img_input})

    def _decode_output(self, output: Any, img_width: int, img_height: int):
        output_array = np.asarray(output)
        if output_array.ndim == 2:
            output_array = np.expand_dims(output_array, axis=0)
        boxes=[]; confidences=[]; class_ids=[]; keypoints_list=[]
        for pred in output_array[0]:
            if pred.shape[0] < 6:
                continue
            x1, y1, x2, y2 = [float(value) for value in pred[:4]]
            confidence = float(pred[4]); class_id = int(pred[5])
            if confidence <= self.conf_threshold:
                continue
            x1 = float(np.clip(x1, 0, img_width)); y1 = float(np.clip(y1, 0, img_height)); x2 = float(np.clip(x2, 0, img_width)); y2 = float(np.clip(y2, 0, img_height))
            boxes.append([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
            confidences.append(confidence); class_ids.append(class_id)
            keypoints=[]
            raw_keypoints = pred[6:]
            if raw_keypoints.size >= 3:
                usable = (raw_keypoints.size // 3) * 3
                reshaped = np.asarray(raw_keypoints[:usable], dtype=np.float32).reshape(-1, 3)
                for kpt_x, kpt_y, kpt_conf in reshaped:
                    keypoints.append((float(np.clip(kpt_x, 0, img_width)), float(np.clip(kpt_y, 0, img_height)), float(kpt_conf)))
            keypoints_list.append(keypoints)
        return boxes, confidences, class_ids, keypoints_list

    def get_class_name(self, class_id: int) -> str:
        return self._class_names[class_id] if 0 <= class_id < len(self._class_names) else f"class_{class_id}"

    def get_keypoint_name(self, index: int) -> str | None:
        return self._keypoint_names[index] if 0 <= index < len(self._keypoint_names) else None

    def _frame_size(self, frame: Any | None) -> tuple[int, int]:
        return (self.imgsz, self.imgsz) if frame is None else (int(frame.shape[1]), int(frame.shape[0]))
    def _parse_metadata_text(self, value: str | None, fallback: str) -> str:
        if not value:
            return fallback
        try: parsed = ast.literal_eval(value)
        except Exception: parsed = value
        return str(parsed).strip().strip("'\"") or fallback
    def _parse_names(self, value: str | None, fallback: list[str]) -> list[str]:
        if not value:
            return fallback
        try: parsed = ast.literal_eval(value)
        except Exception: return fallback
        if isinstance(parsed, dict):
            ordered = [name for _, name in sorted(parsed.items(), key=lambda item: int(item[0]))]
            return [str(name) for name in ordered] or fallback
        if isinstance(parsed, list):
            return [str(item) for item in parsed] or fallback
        return fallback
    def _parse_keypoint_names(self, value: str | None, fallback: list[str]) -> list[str]:
        if not value:
            return fallback
        try: parsed = ast.literal_eval(value)
        except Exception: return fallback
        if isinstance(parsed, dict):
            first = next(iter(parsed.values()), None)
            if isinstance(first, list):
                return [str(item) for item in first] or fallback
        if isinstance(parsed, list):
            return [str(item) for item in parsed] or fallback
        return fallback
