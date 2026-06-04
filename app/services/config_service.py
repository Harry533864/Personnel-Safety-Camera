from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from app.config_schema import validate_ai_config
from app.runtime_paths import AI_CONFIG_PATH
from app.utils import read_yaml, write_yaml


ConfigMutator = Callable[[dict[str, Any]], Any]
ConfigValidator = Callable[[dict[str, Any]], dict[str, Any]]


class ConfigService:
    """Thread-safe read/modify/write access for YAML configuration files."""

    def __init__(
        self,
        path: str | Path,
        validator: ConfigValidator | None = None,
    ) -> None:
        self.path = Path(path)
        self.validator = validator
        self._lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        with self._lock:
            return read_yaml(self.path)

    def write(self, cfg: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.validator is not None:
                self.validator(cfg)
            write_yaml(cfg, file_path=self.path)
            return cfg

    def update(self, mutator: ConfigMutator) -> tuple[dict[str, Any], Any]:
        """Run a mutation while holding the config lock, then validate and save."""
        with self._lock:
            cfg = read_yaml(self.path)
            result = mutator(cfg)
            if self.validator is not None:
                self.validator(cfg)
            write_yaml(cfg, file_path=self.path)
            return cfg, result


ai_config_service = ConfigService(AI_CONFIG_PATH, validator=validate_ai_config)

