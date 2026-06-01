from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Protocol, Sequence


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}
    return bool(value)


def normalize_vision_pipeline(raw: Any = None) -> Dict[str, Any]:
    """
    Internal extension point for future vision tasks.

    This intentionally ships disabled and with no task implementations. Future
    work can register task objects here without changing camera capture,
    streaming, or TensorRT execution flow.
    """
    if not isinstance(raw, Mapping):
        raw = {}

    tasks = raw.get("tasks", {})
    if not isinstance(tasks, Mapping):
        tasks = {}

    return {
        "enabled": _to_bool(raw.get("enabled"), False),
        "tasks": dict(tasks),
    }


@dataclass
class VisionTaskContext:
    detections: Sequence[Any]
    frame_result: Any = None
    image_shape: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisionTaskResult:
    task_id: str
    enabled: bool = True
    ok: bool = True
    alarm: bool = False
    warning: bool = False
    count: int = 0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.task_id,
            "enabled": self.enabled,
            "ok": self.ok,
            "alarm": self.alarm,
            "warning": self.warning,
            "count": self.count,
            "message": self.message,
            "details": self.details,
        }


class VisionTask(Protocol):
    task_id: str

    def evaluate(self, context: VisionTaskContext, config: Mapping[str, Any]) -> VisionTaskResult:
        ...


class VisionTaskManager:
    def __init__(self, pipeline_config: Any = None):
        self.config = normalize_vision_pipeline(pipeline_config)
        self._registry: Dict[str, VisionTask] = {}

    def register(self, task: VisionTask) -> None:
        task_id = str(getattr(task, "task_id", "")).strip()
        if not task_id:
            raise ValueError("VisionTask.task_id 不能为空")
        self._registry[task_id] = task

    def evaluate(
        self,
        detections: Sequence[Any],
        frame_result: Any = None,
        image_shape: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        if not self.config.get("enabled"):
            return []

        task_configs = self.config.get("tasks", {})
        if not isinstance(task_configs, Mapping) or not task_configs:
            return []

        context = VisionTaskContext(
            detections=detections,
            frame_result=frame_result,
            image_shape=image_shape,
            metadata=dict(metadata or {}),
        )

        results: List[Dict[str, Any]] = []
        for task_id, task_config in task_configs.items():
            task = self._registry.get(str(task_id))
            if task is None:
                continue
            if isinstance(task_config, Mapping) and not _to_bool(task_config.get("enabled"), True):
                continue
            result = task.evaluate(context, task_config if isinstance(task_config, Mapping) else {})
            results.append(result.to_dict())

        return results

    @staticmethod
    def has_alarm(results: Sequence[Mapping[str, Any]]) -> bool:
        return any(bool(result.get("alarm")) for result in results)

    @staticmethod
    def has_warning(results: Sequence[Mapping[str, Any]]) -> bool:
        return any(bool(result.get("warning")) for result in results)
