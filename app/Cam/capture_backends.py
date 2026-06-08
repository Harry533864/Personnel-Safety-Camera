from __future__ import annotations

import logging
import os
import time
from typing import Any

import cv2
import numpy as np


class BaumerNeoApiCapture:
    """OpenCV-like capture wrapper for Baumer VAX/AX smart cameras."""

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        exposure_us: int = 0,
        gain_db: float = 0.0,
        white_balance: str = "continuous",
        pixel_format: str = "BGR8",
        connect_retries: int = 3,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))
        self.exposure_us = int(exposure_us or 0)
        self.gain_db = float(gain_db or 0)
        self.white_balance = self._normalize_white_balance(white_balance)
        self.pixel_format = str(pixel_format or "BGR8")
        self.connect_retries = max(1, int(connect_retries))
        self.camera: Any | None = None
        self.neoapi: Any | None = None
        self.logger = logging.getLogger(__name__)
        self.last_error: str | None = None

    def open(self) -> bool:
        try:
            import neoapi
        except Exception as exc:
            self.last_error = f"neoapi import failed: {exc}"
            self.logger.exception("neoapi is required for Baumer capture")
            return False

        self.neoapi = neoapi
        for attempt in range(1, self.connect_retries + 1):
            try:
                camera = neoapi.Cam()
                camera.Connect()
                self.camera = camera
                self._configure_camera()
                self.last_error = None
                self.logger.info(
                    "Baumer neoAPI capture opened: %sx%s@%s pixel_format=%s",
                    self.width,
                    self.height,
                    self.fps,
                    self.pixel_format,
                )
                return True
            except Exception as exc:
                self.last_error = str(exc)
                self.logger.warning(
                    "Baumer camera open failed attempt=%s/%s: %s",
                    attempt,
                    self.connect_retries,
                    exc,
                )
                self.release()
                time.sleep(0.5)
        return False

    def isOpened(self) -> bool:
        return self.camera is not None

    def read(self):
        if self.camera is None:
            return False, None

        try:
            image = self.camera.GetImage()
            if image is None or (hasattr(image, "IsEmpty") and image.IsEmpty()):
                return False, None

            frame = image.GetNPArray()
            frame = self._normalize_frame(frame)
            return True, frame
        except Exception as exc:
            self.last_error = str(exc)
            self.logger.warning("Baumer frame read failed: %s", exc)
            return False, None

    def release(self) -> None:
        camera = self.camera
        self.camera = None
        if camera is None:
            return
        for method_name in ("Disconnect", "Close"):
            method = getattr(camera, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    self.logger.debug("Ignored Baumer camera %s error", method_name, exc_info=True)
                break

    def describe(self) -> str:
        return (
            "baumer_neoapi "
            f"width={self.width} height={self.height} fps={self.fps} "
            f"pixel_format={self.pixel_format}"
        )

    def set_exposure(self, exposure_us: int) -> None:
        self.exposure_us = int(exposure_us or 0)
        if self.camera is not None:
            self._configure_exposure()
            self._configure_gain()

    def set_gain(self, gain_db: float) -> None:
        self.gain_db = float(gain_db or 0)
        if self.camera is not None:
            self._configure_gain()

    def set_white_balance(self, mode: str) -> None:
        self.white_balance = self._normalize_white_balance(mode)
        if self.camera is not None:
            self._configure_white_balance()

    def _normalize_white_balance(self, mode: str) -> str:
        value = str(mode or "continuous").strip().lower()
        aliases = {
            "auto": "continuous",
            "on": "continuous",
            "true": "continuous",
            "1": "continuous",
            "continuous": "continuous",
            "once": "once",
            "single": "once",
            "off": "off",
            "manual": "off",
            "false": "off",
            "0": "off",
        }
        return aliases.get(value, "continuous")

    def _feature(self, name: str):
        if self.camera is None:
            return None
        features = getattr(self.camera, "f", None)
        return getattr(features, name, None) if features is not None else None

    def _set_feature(self, name: str, value: Any) -> bool:
        feature = self._feature(name)
        setter = getattr(feature, "Set", None)
        if not callable(setter):
            return False
        try:
            setter(value)
            return True
        except Exception as exc:
            self.logger.info("Baumer feature %s=%r not applied: %s", name, value, exc)
            return False

    def _enum_value(self, feature_name: str, value: str):
        if self.neoapi is None:
            return None

        normalized = str(value).strip().replace(" ", "").replace("-", "")
        candidates = [
            f"{feature_name}_{normalized}",
            f"{feature_name}_{normalized.capitalize()}",
            f"{feature_name}_{normalized.upper()}",
        ]
        for candidate in candidates:
            enum_value = getattr(self.neoapi, candidate, None)
            if enum_value is not None:
                return enum_value
        return None

    def _set_enum_feature(self, name: str, value: str) -> bool:
        enum_value = self._enum_value(name, value)
        if enum_value is not None and self._set_feature(name, enum_value):
            return True
        return self._set_feature(name, value)

    def _env_float(self, name: str, default: float | None = None) -> float | None:
        raw = os.environ.get(name)
        if raw is None or str(raw).strip() == "":
            return default
        try:
            return float(raw)
        except ValueError:
            self.logger.warning("Ignored invalid %s=%r", name, raw)
            return default

    def _set_numeric_feature(self, name: str, value: float | None) -> bool:
        if value is None:
            return False
        return self._set_feature(name, float(value))

    def _configure_auto_exposure_limits(self) -> None:
        brightness = self._env_float("BAUMER_BRIGHTNESS_AUTO_NOMINAL", 28.0)
        exposure_min = self._env_float("BAUMER_EXPOSURE_AUTO_MIN_US", None)
        exposure_max = self._env_float("BAUMER_EXPOSURE_AUTO_MAX_US", 12000.0)
        gain_min = self._env_float("BAUMER_GAIN_AUTO_MIN", 1.0)
        gain_max = self._env_float("BAUMER_GAIN_AUTO_MAX", 32.0)
        priority = os.environ.get("BAUMER_BRIGHTNESS_AUTO_PRIORITY", "ExposureAuto").strip()

        applied = {
            "BrightnessAutoNominalValue": self._set_numeric_feature("BrightnessAutoNominalValue", brightness),
            "ExposureAutoMinValue": self._set_numeric_feature("ExposureAutoMinValue", exposure_min),
            "ExposureAutoMaxValue": self._set_numeric_feature("ExposureAutoMaxValue", exposure_max),
            "GainAutoMinValue": self._set_numeric_feature("GainAutoMinValue", gain_min),
            "GainAutoMaxValue": self._set_numeric_feature("GainAutoMaxValue", gain_max),
        }
        priority_ok = self._set_enum_feature("BrightnessAutoPriority", priority) if priority else False
        self.logger.info(
            "Baumer auto exposure limits: brightness=%s exposure_min=%s exposure_max=%s "
            "gain_min=%s gain_max=%s priority=%s applied=%s priority_ok=%s",
            brightness,
            exposure_min,
            exposure_max,
            gain_min,
            gain_max,
            priority or None,
            applied,
            priority_ok,
        )

    def _configure_camera(self) -> None:
        # Order matters on many industrial cameras: pixel format first, then ROI.
        self._set_pixel_format()
        self._set_feature("Width", self.width)
        self._set_feature("Height", self.height)
        self._set_feature("AcquisitionFrameRateEnable", True)
        self._set_feature("AcquisitionFrameRate", float(self.fps))
        self._configure_exposure()
        self._configure_gain()
        self._configure_white_balance()

    def _set_pixel_format(self) -> None:
        pixel_format = self.pixel_format.strip()
        if not pixel_format:
            return

        enum_value = None
        if self.neoapi is not None:
            enum_value = getattr(self.neoapi, f"PixelFormat_{pixel_format}", None)
            if enum_value is None:
                enum_value = getattr(self.neoapi, f"PixelFormat_{pixel_format.upper()}", None)

        if enum_value is not None and self._set_feature("PixelFormat", enum_value):
            return

        self._set_feature("PixelFormat", pixel_format)

    def _configure_exposure(self) -> None:
        if self.exposure_us > 0:
            self._set_enum_feature("ExposureMode", "Timed")
            self._set_enum_feature("ExposureAuto", "Off")
            self._set_enum_feature("GainAuto", "Off")
            self._set_feature("ExposureTime", float(self.exposure_us))
            self._configure_white_balance()
            self.logger.info("Baumer manual exposure requested: %sus", self.exposure_us)
        else:
            # Keep automatic exposure as the safe production default.
            self._set_enum_feature("ExposureMode", "Timed")
            self._configure_auto_exposure_limits()
            exposure_ok = self._set_enum_feature("ExposureAuto", "Continuous")
            gain_ok = self._set_enum_feature("GainAuto", "Continuous")
            white_ok = self._configure_white_balance()
            self.logger.info(
                "Baumer auto exposure requested: exposure_auto=%s gain_auto=%s white_auto=%s",
                exposure_ok,
                gain_ok,
                white_ok,
            )

    def _configure_gain(self) -> None:
        if self.gain_db > 0:
            self._set_enum_feature("GainAuto", "Off")
            gain_ok = self._set_feature("Gain", float(self.gain_db))
            self.logger.info("Baumer manual gain requested: %sdB applied=%s", self.gain_db, gain_ok)
        else:
            gain_ok = self._set_enum_feature("GainAuto", "Continuous")
            self.logger.info("Baumer auto gain requested: gain_auto=%s", gain_ok)

    def _configure_white_balance(self) -> bool:
        value = {
            "continuous": "Continuous",
            "once": "Once",
            "off": "Off",
        }.get(self.white_balance, "Continuous")
        ok = self._set_enum_feature("BalanceWhiteAuto", value)
        self.logger.info("Baumer white balance requested: %s applied=%s", value, ok)
        return ok

    def _normalize_frame(self, frame):
        if frame is None:
            return None

        if not isinstance(frame, np.ndarray):
            frame = np.asarray(frame)

        if frame.ndim == 3 and frame.shape[2] == 1:
            frame = frame[:, :, 0]

        if frame.ndim == 2:
            pixel_format = self.pixel_format.strip().upper()
            if pixel_format.startswith("BAYER"):
                bayer_conversions = {
                    "BAYERRG8": cv2.COLOR_BAYER_RG2BGR,
                    "BAYERBG8": cv2.COLOR_BAYER_BG2BGR,
                    "BAYERGB8": cv2.COLOR_BAYER_GB2BGR,
                    "BAYERGR8": cv2.COLOR_BAYER_GR2BGR,
                }
                conversion = bayer_conversions.get(pixel_format)
                if conversion is not None:
                    frame = cv2.cvtColor(frame, conversion)
            return np.ascontiguousarray(frame)

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 3:
            pixel_format = self.pixel_format.strip().upper()
            if pixel_format.startswith("RGB"):
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
        return frame
