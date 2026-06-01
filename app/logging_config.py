import logging
import os
from logging.handlers import RotatingFileHandler

from app.runtime_paths import LOG_DIR


_CONFIGURED = False


def configure_logging():
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.environ.get("CAM_LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
    level = getattr(logging, level_name.upper(), logging.INFO)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(fmt))
        root_logger.addHandler(console_handler)

    log_file = os.environ.get("CAM_LOG_FILE")
    if log_file is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = str(LOG_DIR / "backend.log")

    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=int(os.environ.get("CAM_LOG_MAX_BYTES", "5242880")),
            backupCount=int(os.environ.get("CAM_LOG_BACKUP_COUNT", "3")),
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(fmt))
        root_logger.addHandler(file_handler)

    _CONFIGURED = True
