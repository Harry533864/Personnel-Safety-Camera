from __future__ import annotations

import logging
import sys
import time
from typing import Any

from .ysl301 import (
    CHANNELS,
    DEFAULT_IDLE_PATTERN,
    LIGHT_STATES,
    Ysl301Config,
    Ysl301Light,
    normalize_state_name,
)

try:
    import Jetson.GPIO as GPIO
except Exception:  # pragma: no cover - Jetson.GPIO only exists on target hardware.
    GPIO = None


logger = logging.getLogger(__name__)


class AlarmOutputController:
    def __init__(self, cfg: dict[str, Any] | None) -> None:
        cfg = cfg or {}
        self.cfg = cfg

        self.gpio_pins: list[int] = []
        self.gpio_alarm_level = 1
        self.gpio_idle_level = 0

        self.serial_light: Ysl301Light | None = None
        self.serial_error: str | None = None
        self.serial_retry_interval = 1.0
        self._serial_next_retry_at = 0.0

        self.duration = float(cfg.get("duration", 0) or 0)
        self.alarm_active = False
        self.output_on = False
        self.output_end_time: float | None = None
        self.current_state: str | None = None
        self.manual_override_until = 0.0
        self.manual_override_seconds = 2.5

        self._init_gpio()
        self._init_serial(force=True)
        self.set_state("safe", force=True)

    def set_alarm(self, alarm_flag: bool) -> None:
        self.set_state("alarm" if alarm_flag else "safe")

    def set_state(self, state: object, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now < self.manual_override_until:
            return

        state_key = self._normalize_output_state(state)
        if state_key != "alarm":
            needs_serial_retry = self.serial_light is None and self.serial_error
            if force or self.current_state != state_key or needs_serial_retry:
                self._write_state(state_key, force_retry=force)
            self.alarm_active = False
            self.output_on = state_key != "safe"
            self.output_end_time = None
            return

        if not self.alarm_active:
            self.alarm_active = True
            self.output_on = True
            self._write_state("alarm", force_retry=force)
            self.output_end_time = now + self.duration if self.duration > 0 else None
            return

        if self.current_state != "alarm" or (self.serial_light is None and self.serial_error):
            self._write_state("alarm", force_retry=force)

        if (
            self.duration > 0
            and self.output_on
            and self.output_end_time is not None
            and now >= self.output_end_time
        ):
            self._write_state("safe", force_retry=force)
            self.output_on = False

    def set_manual_channels(self, states: dict[str, Any]) -> bool:
        pattern = self._manual_pattern(states)
        active_channels = [
            channel for channel, state in pattern.items()
            if state != "off"
        ]
        active = bool(active_channels)
        gpio_active = pattern.get("buzzer") != "off"

        self.manual_override_until = time.monotonic() + self.manual_override_seconds
        self.alarm_active = active
        self.output_on = active
        self.output_end_time = None
        self.current_state = "manual"

        if self.gpio_pins:
            self._write_gpio(gpio_active)

        serial_ok = self._write_serial_pattern(pattern, force_retry=True)
        gpio_ok = bool(self.gpio_pins) and set(active_channels).issubset({"buzzer"})
        if serial_ok or gpio_ok:
            return True
        if active and self.serial_error:
            raise RuntimeError(self.serial_error)
        return False

    def all_off(self) -> bool:
        self.manual_override_until = time.monotonic() + self.manual_override_seconds
        self.alarm_active = False
        self.output_on = False
        self.output_end_time = None
        self.current_state = "off"
        self._write_gpio(False)
        return self._write_serial_pattern(DEFAULT_IDLE_PATTERN, force_retry=True)

    def close(self) -> None:
        self._release_gpio()
        if self.serial_light is not None:
            try:
                self.serial_light.apply_pattern(DEFAULT_IDLE_PATTERN)
            except Exception:
                logger.exception("Failed to turn off YSL301 alarm output")
            self.serial_light.close()
            self.serial_light = None

    def _init_gpio(self) -> None:
        gpio = self.cfg.get("gpio")
        if not gpio:
            return

        if GPIO is None:
            print("[alarm_gpio] Jetson.GPIO not installed; GPIO alarm output skipped", file=sys.stderr)
            return

        pins = gpio if isinstance(gpio, list) else [gpio]
        normalized_pins = []
        for pin in pins:
            try:
                pin_number = int(pin)
            except Exception:
                continue
            if pin_number > 0:
                normalized_pins.append(pin_number)

        self.gpio_pins = sorted(set(normalized_pins))
        if not self.gpio_pins:
            return

        self.gpio_alarm_level = 1 if int(self.cfg.get("output_level", 1)) else 0
        self.gpio_idle_level = 0 if self.gpio_alarm_level == 1 else 1

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BOARD)
            for pin in self.gpio_pins:
                GPIO.setup(pin, GPIO.OUT, initial=self.gpio_idle_level)
        except Exception as exc:
            logger.warning("GPIO alarm output disabled: %s", exc)
            try:
                GPIO.cleanup(self.gpio_pins)
            except Exception:
                logger.debug("Ignored GPIO cleanup failure after setup error", exc_info=True)
            self.gpio_pins = []

    def _init_serial(self, force: bool = False) -> bool:
        if self.serial_light is not None:
            return True

        now = time.monotonic()
        if not force and now < self._serial_next_retry_at:
            return False

        serial_cfg = self.cfg.get("serial", {}) or {}
        self.serial_retry_interval = float(
            serial_cfg.get("retry_interval", serial_cfg.get("retryInterval", self.serial_retry_interval)) or 1.0
        )
        ysl_cfg = Ysl301Config.from_mapping(serial_cfg)
        if not ysl_cfg.enabled:
            self.serial_error = "serial alarm output is disabled"
            self._serial_next_retry_at = now + self.serial_retry_interval
            return False

        try:
            self.serial_light = Ysl301Light(ysl_cfg)
            self.serial_error = None
            self._serial_next_retry_at = 0.0
            logger.info("YSL301 alarm output initialized on %s", self.serial_light.port)
            return True
        except Exception as exc:
            self.serial_error = str(exc)
            self._serial_next_retry_at = now + self.serial_retry_interval
            logger.warning("YSL301 alarm output disabled: %s", exc)
            self.serial_light = None
            return False

    def _drop_serial(self, exc: Exception) -> None:
        self.serial_error = str(exc)
        self._serial_next_retry_at = time.monotonic() + self.serial_retry_interval
        if self.serial_light is not None:
            try:
                self.serial_light.close()
            except Exception:
                logger.exception("Failed to close failed YSL301 serial port")
        self.serial_light = None

    @staticmethod
    def _normalize_output_state(state: object) -> str:
        state_key = str(getattr(state, "value", state) or "safe").strip().lower()
        if state_key in {"alarm", "prestart_blocked"}:
            return "alarm"
        if state_key == "warning":
            return "warning"
        return "safe"

    def _write_state(self, state: str, force_retry: bool = False) -> None:
        state_key = self._normalize_output_state(state)
        self._write_gpio(state_key == "alarm")
        serial_ok = self._write_serial_state(state_key, force_retry=force_retry)
        if serial_ok or self.serial_light is not None or self.gpio_pins:
            self.current_state = state_key

    def _write_gpio(self, active: bool) -> None:
        if not self.gpio_pins or GPIO is None:
            return

        level = self.gpio_alarm_level if active else self.gpio_idle_level
        for pin in self.gpio_pins:
            try:
                GPIO.output(pin, level)
            except RuntimeError:
                GPIO.setup(pin, GPIO.OUT, initial=self.gpio_idle_level)
                GPIO.output(pin, level)

    def _write_serial_state(self, state: str, force_retry: bool = False) -> bool:
        if not self._init_serial(force=force_retry):
            return False

        try:
            if state == "alarm":
                self.serial_light.apply_pattern(self.serial_light.config.alarm)
            elif state == "warning":
                self.serial_light.apply_pattern(self.serial_light.config.warning)
            else:
                self.serial_light.apply_pattern(self.serial_light.config.safe)
            self.serial_error = None
            return True
        except Exception as exc:
            logger.warning("YSL301 alarm write failed: %s", exc)
            self._drop_serial(exc)
            return False

    def _write_serial_pattern(self, pattern: dict[str, str], force_retry: bool = False) -> bool:
        if not self._init_serial(force=force_retry):
            return False

        try:
            self.serial_light.apply_pattern(pattern)
            self.serial_error = None
            return True
        except Exception as exc:
            logger.warning("YSL301 manual alarm write failed: %s", exc)
            self._drop_serial(exc)
            return False

    @staticmethod
    def _manual_pattern(states: dict[str, Any]) -> dict[str, str]:
        pattern = dict(DEFAULT_IDLE_PATTERN)
        for channel, state in (states or {}).items():
            channel_key = str(channel).strip().lower()
            if channel_key not in CHANNELS:
                raise ValueError(f"Unsupported YSL301 channel: {channel}")

            state_key = normalize_state_name(state)
            if state_key not in LIGHT_STATES:
                raise ValueError(f"Unsupported YSL301 state: {state}")

            pattern[channel_key] = state_key
        return pattern

    def _release_gpio(self) -> None:
        if self.gpio_pins and GPIO is not None:
            try:
                for pin in self.gpio_pins:
                    GPIO.output(pin, self.gpio_idle_level)
                GPIO.cleanup(self.gpio_pins)
            except Exception:
                logger.exception("Failed to release GPIO alarm output")
        self.gpio_pins = []
