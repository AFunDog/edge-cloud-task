from edge_cloud_system.domain.models import BoundingBox, Detection, Keypoint, PoseAction
from edge_cloud_system.edge.pose import PoseAnalyzer


def _make_keypoints() -> list[Keypoint]:
    return [Keypoint(x=0.0, y=0.0, confidence=0.0) for _ in range(17)]


def test_pose_analyzer_recognizes_raised_hand() -> None:
    keypoints = _make_keypoints()
    keypoints[5] = Keypoint(x=100.0, y=200.0, confidence=0.95)
    keypoints[6] = Keypoint(x=150.0, y=200.0, confidence=0.95)
    keypoints[11] = Keypoint(x=102.0, y=320.0, confidence=0.9)
    keypoints[12] = Keypoint(x=148.0, y=320.0, confidence=0.9)
    keypoints[9] = Keypoint(x=98.0, y=150.0, confidence=0.92)
    keypoints[10] = Keypoint(x=152.0, y=210.0, confidence=0.92)

    detection = Detection(
        label="person",
        confidence=0.97,
        box=BoundingBox(x1=60.0, y1=80.0, x2=220.0, y2=360.0),
        keypoints=keypoints,
    )

    decision = PoseAnalyzer().analyze([detection], (640, 360))

    assert decision.analysis.action == PoseAction.RAISING_HAND
    assert decision.analysis.needs_cloud is False
    assert decision.analysis.confidence > 0.6


def test_pose_analyzer_marks_cloud_when_keypoints_are_sparse() -> None:
    keypoints = _make_keypoints()
    keypoints[5] = Keypoint(x=100.0, y=200.0, confidence=0.2)
    keypoints[6] = Keypoint(x=150.0, y=200.0, confidence=0.2)

    detection = Detection(
        label="person",
        confidence=0.9,
        box=BoundingBox(x1=50.0, y1=60.0, x2=210.0, y2=340.0),
        keypoints=keypoints,
    )

    decision = PoseAnalyzer().analyze([detection], (640, 360))

    assert decision.analysis.action == PoseAction.UNKNOWN
    assert decision.analysis.needs_cloud is True
