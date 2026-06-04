from __future__ import annotations

import logging
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
        pixel_format: str = "BGR8",
        connect_retries: int = 3,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))
        self.exposure_us = int(exposure_us or 0)
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

    def _configure_camera(self) -> None:
        # Order matters on many industrial cameras: pixel format first, then ROI.
        self._set_pixel_format()
        self._set_feature("Width", self.width)
        self._set_feature("Height", self.height)
        self._set_feature("AcquisitionFrameRateEnable", True)
        self._set_feature("AcquisitionFrameRate", float(self.fps))
        self._configure_exposure()

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
            self._set_feature("ExposureAuto", "Off")
            self._set_feature("ExposureTime", float(self.exposure_us))
        else:
            # Keep automatic exposure as the safe production default.
            self._set_feature("ExposureAuto", "Continuous")

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
