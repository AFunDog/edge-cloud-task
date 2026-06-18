import numpy as np
import pytest

from backend.edge_api.runtime.detector import DEFAULT_KEYPOINT_NAMES, YoloDetector


def _detector_for_decode() -> YoloDetector:
    detector = object.__new__(YoloDetector)
    detector.conf_threshold = 0.25
    detector._model_task = "pose"
    detector._class_names = ["person"]
    detector._keypoint_names = list(DEFAULT_KEYPOINT_NAMES)
    return detector


def test_decode_pose_output_transposes_raw_onnx_and_maps_xywh() -> None:
    detector = _detector_for_decode()
    pred = np.zeros(4 + 1 + 17 * 3, dtype=np.float32)
    pred[:5] = [320.0, 240.0, 160.0, 200.0, 0.92]
    pred[5 + 5 * 3 : 5 + 5 * 3 + 3] = [280.0, 220.0, 0.95]
    pred[5 + 6 * 3 : 5 + 6 * 3 + 3] = [360.0, 220.0, 0.96]
    pred[5 + 11 * 3 : 5 + 11 * 3 + 3] = [290.0, 340.0, 0.91]

    output = np.zeros((1, pred.shape[0], 100), dtype=np.float32)
    output[0, :, 0] = pred

    boxes, confidences, class_ids, keypoints = detector._decode_output(output, 640, 640)

    assert boxes == [[240.0, 140.0, 400.0, 340.0]]
    assert confidences == pytest.approx([0.92])
    assert class_ids == [0]
    assert keypoints[0][5] == pytest.approx((280.0, 220.0, 0.95))
    assert keypoints[0][6] == pytest.approx((360.0, 220.0, 0.96))
    assert keypoints[0][11] == pytest.approx((290.0, 340.0, 0.91))


def test_decode_nms_output_keeps_xyxy_boxes() -> None:
    detector = _detector_for_decode()
    pred = np.zeros(6 + 17 * 3, dtype=np.float32)
    pred[:6] = [10.0, 20.0, 110.0, 220.0, 0.8, 0.0]
    pred[6 + 5 * 3 : 6 + 5 * 3 + 3] = [40.0, 60.0, 0.9]

    boxes, confidences, class_ids, keypoints = detector._decode_output(pred.reshape(1, 1, -1), 640, 640)

    assert boxes == [[10.0, 20.0, 110.0, 220.0]]
    assert confidences == pytest.approx([0.8])
    assert class_ids == [0]
    assert keypoints[0][5] == pytest.approx((40.0, 60.0, 0.9))
