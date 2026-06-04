from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from app.config_schema import validate_ai_config
from app.runtime_paths import AI_CONFIG_PATH
from app.utils import read_yaml, write_yaml


ConfigData = Dict[str, Any]
ConfigMutator = Callable[[ConfigData], Any]
ConfigValidator = Callable[[ConfigData], ConfigData]


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

    def read(self) -> ConfigData:
        with self._lock:
            return read_yaml(self.path)

    def write(self, cfg: ConfigData) -> ConfigData:
        with self._lock:
            if self.validator is not None:
                self.validator(cfg)
            write_yaml(cfg, file_path=self.path)
            return cfg

    def update(self, mutator: ConfigMutator) -> Tuple[ConfigData, Any]:
        """Run a mutation while holding the config lock, then validate and save."""
        with self._lock:
            cfg = read_yaml(self.path)
            result = mutator(cfg)
            if self.validator is not None:
                self.validator(cfg)
            write_yaml(cfg, file_path=self.path)
            return cfg, result


ai_config_service = ConfigService(AI_CONFIG_PATH, validator=validate_ai_config)
