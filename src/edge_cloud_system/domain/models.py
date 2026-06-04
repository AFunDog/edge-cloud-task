from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class ExecutionTarget(str, Enum):
    EDGE = "edge"
    CLOUD = "cloud"


class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class Detection(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    box: BoundingBox


class DetectionResult(BaseModel):
    device_id: str
    frame_id: str = Field(default_factory=lambda: uuid4().hex)
    fps: float = 0
    inference_ms: float = 0
    backend: str = ""
    model_path: str = ""
    frame_width: int = 640
    frame_height: int = 360
    image_jpeg_base64: str | None = None
    detections: list[Detection] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EdgeStatus(BaseModel):
    device_id: str
    online: bool = True
    network: str = "Wi-Fi"
    fps: float = 0
    cpu_percent: float = 0
    memory_percent: float = 0
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskRequest(BaseModel):
    task: str
    device_id: str
    frame_id: str | None = None
    context: dict = Field(default_factory=dict)


class ScheduleDecision(BaseModel):
    target: ExecutionTarget
    complexity: TaskComplexity
    reason: str


class TaskLog(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    task: str
    device_id: str
    target: ExecutionTarget
    result_summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRequest(BaseModel):
    question: str
    device_id: str | None = None
    context: dict = Field(default_factory=dict)


class AgentResponse(BaseModel):
    answer: str
    used_search: bool = False
    used_knowledge: bool = False
    traces: list[str] = Field(default_factory=list)
