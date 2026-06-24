from __future__ import annotations

import glob
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

try:
    import serial
    from serial.tools import list_ports
except Exception:  # pragma: no cover - pyserial is optional until hardware is used.
    serial = None
    list_ports = None

try:
    import termios
except Exception:  # pragma: no cover - termios is not available on Windows.
    termios = None


logger = logging.getLogger(__name__)


CHANNELS = {
    "red": 0x0000,
    "yellow": 0x0001,
    "green": 0x0002,
    "buzzer": 0x0003,
}

LIGHT_STATES = {
    "off": 0x0000,
    "close": 0x0000,
    "false": 0x0000,
    "0": 0x0000,
    "on": 0xFF00,
    "open": 0xFF00,
    "true": 0xFF00,
    "1": 0xFF00,
    "blink2hz": 0xF000,
    "tweet2hz": 0xF000,
    "2hz": 0xF000,
    "blink1hz": 0xF100,
    "tweet1hz": 0xF100,
    "1hz": 0xF100,
    "blink0_5hz": 0xF200,
    "tweet0_5hz": 0xF200,
    "0.5hz": 0xF200,
    "blink0_25hz": 0xF300,
    "tweet0_25hz": 0xF300,
    "0.25hz": 0xF300,
}

DEFAULT_ALARM_PATTERN = {
    "red": "on",
    "yellow": "off",
    "green": "off",
    "buzzer": "on",
}

DEFAULT_WARNING_PATTERN = {
    "red": "off",
    "yellow": "on",
    "green": "off",
    "buzzer": "off",
}

DEFAULT_SAFE_PATTERN = {
    "red": "off",
    "yellow": "off",
    "green": "on",
    "buzzer": "off",
}

DEFAULT_IDLE_PATTERN = {
    "red": "off",
    "yellow": "off",
    "green": "off",
    "buzzer": "off",
}

BAUDRATES = {}
if termios is not None:
    BAUDRATES = {
        300: termios.B300,
        600: termios.B600,
        1200: termios.B1200,
        2400: termios.B2400,
        4800: termios.B4800,
        9600: termios.B9600,
        19200: termios.B19200,
        38400: termios.B38400,
        57600: termios.B57600,
        115200: termios.B115200,
    }


def crc16_modbus(data: bytes | bytearray | Iterable[int]) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= int(value) & 0xFF
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc


def build_write_coil_frame(address: int, channel: str, state: str) -> bytes:
    if channel not in CHANNELS:
        raise ValueError(f"Unsupported YSL301 channel: {channel}")

    state_key = normalize_state_name(state)
    if state_key not in LIGHT_STATES:
        raise ValueError(f"Unsupported YSL301 state: {state}")

    address = int(address)
    if not 0 < address <= 0xFF:
        raise ValueError("YSL301 address must be between 1 and 255")

    coil = CHANNELS[channel]
    value = LIGHT_STATES[state_key]
    frame = bytearray(
        [
            address,
            0x05,
            (coil >> 8) & 0xFF,
            coil & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
    )
    crc = crc16_modbus(frame)
    frame.extend([crc & 0xFF, (crc >> 8) & 0xFF])
    return bytes(frame)


def normalize_state_name(value: str | int | bool | None) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value if value is not None else "off").strip().lower().replace("-", "_")


def normalize_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    value_str = str(value).strip().lower()
    if value_str in {"1", "true", "yes", "on", "enabled"}:
        return True
    if value_str in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def ch340_usb_present() -> bool:
    usb_root = Path("/sys/bus/usb/devices")
    if not usb_root.exists():
        return False

    for vendor_file in usb_root.glob("*/idVendor"):
        try:
            vendor = vendor_file.read_text(encoding="ascii").strip().lower()
            product = (vendor_file.parent / "idProduct").read_text(encoding="ascii").strip().lower()
        except Exception:
            continue
        if vendor == "1a86" and product == "7523":
            return True
    return False


def discover_serial_ports(*, include_board_uart: bool = False) -> list[str]:
    candidates: list[str] = []

    if list_ports is not None:
        for port in list_ports.comports():
            device = getattr(port, "device", None)
            if not device:
                continue

            vid = getattr(port, "vid", None)
            description = f"{getattr(port, 'description', '')} {getattr(port, 'manufacturer', '')}".lower()
            is_usb_serial = (
                vid is not None
                or str(device).startswith(("/dev/ttyUSB", "/dev/ttyACM"))
                or str(device).startswith("COM")
            )
            if vid == 0x1A86 or "ch340" in description or "ch341" in description:
                candidates.insert(0, device)
            elif include_board_uart or is_usb_serial:
                candidates.append(device)

    for pattern in (
        "/dev/serial/by-id/*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "COM*",
    ):
        for path in glob.glob(pattern):
            device = str(Path(path))
            if device not in candidates:
                candidates.append(device)

    if include_board_uart:
        for pattern in ("/dev/ttyTHS*", "/dev/ttyS*"):
            for path in glob.glob(pattern):
                device = str(Path(path))
                if device not in candidates:
                    candidates.append(device)

    return candidates


def resolve_serial_port(port: str | None) -> str:
    port = str(port or "auto").strip()
    port_key = port.lower()
    if port and port_key not in {"auto", "auto-board", "board-auto", "all-auto"}:
        return port

    candidates = discover_serial_ports(include_board_uart=port_key in {"auto-board", "board-auto", "all-auto"})
    if not candidates:
        if ch340_usb_present():
            raise RuntimeError(
                "CH340 USB serial adapter is connected, but no /dev/ttyUSB* serial device exists; "
                "load/install the ch341 driver or bind usbserial for 1a86:7523"
            )
        raise RuntimeError("No YSL301 serial port found; set exception_output.serial.port")
    return candidates[0]


@dataclass(frozen=True)
class Ysl301Config:
    enabled: bool = False
    port: str = "auto"
    baudrate: int = 9600
    address: int = 1
    timeout: float = 0.5
    write_timeout: float = 0.5
    command_delay: float = 0.05
    alarm: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_ALARM_PATTERN))
    warning: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_WARNING_PATTERN))
    safe: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_SAFE_PATTERN))
    idle: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_IDLE_PATTERN))

    @classmethod
    def from_mapping(cls, cfg: Mapping[str, object] | None) -> "Ysl301Config":
        cfg = cfg or {}
        enabled = normalize_bool(cfg.get("enabled"), False)
        return cls(
            enabled=enabled,
            port=str(cfg.get("port", "auto") or "auto"),
            baudrate=int(cfg.get("baudrate", 9600) or 9600),
            address=int(cfg.get("address", 1) or 1),
            timeout=float(cfg.get("timeout", 0.5) or 0.5),
            write_timeout=float(cfg.get("write_timeout", cfg.get("writeTimeout", 0.5)) or 0.5),
            command_delay=float(cfg.get("command_delay", cfg.get("commandDelay", 0.05)) or 0.05),
            alarm=normalize_pattern(cfg.get("alarm"), DEFAULT_ALARM_PATTERN),
            warning=normalize_pattern(cfg.get("warning"), DEFAULT_WARNING_PATTERN),
            safe=normalize_pattern(cfg.get("safe"), DEFAULT_SAFE_PATTERN),
            idle=normalize_pattern(cfg.get("idle"), DEFAULT_IDLE_PATTERN),
        )


def normalize_pattern(raw: object, defaults: Mapping[str, str]) -> dict[str, str]:
    pattern = dict(defaults)
    if isinstance(raw, Mapping):
        for channel, state in raw.items():
            channel_key = str(channel).strip().lower()
            if channel_key in CHANNELS:
                pattern[channel_key] = normalize_state_name(state)
    return pattern


class Ysl301Light:
    def __init__(self, config: Ysl301Config) -> None:
        self.config = config
        self.port = resolve_serial_port(config.port)
        if serial is not None:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=config.baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=config.timeout,
                write_timeout=config.write_timeout,
            )
        else:
            if termios is None:
                raise RuntimeError("pyserial is not installed and termios is unavailable")
            self._serial = TermiosSerial(self.port, config.baudrate)

    def set_channel(self, channel: str, state: str) -> None:
        frame = build_write_coil_frame(self.config.address, channel, state)
        self._serial.reset_output_buffer()
        self._serial.write(frame)
        self._serial.flush()
        if self.config.command_delay > 0:
            time.sleep(self.config.command_delay)

    def apply_pattern(self, pattern: Mapping[str, str]) -> None:
        for channel in ("red", "yellow", "green", "buzzer"):
            state = normalize_state_name(pattern.get(channel, "off"))
            self.set_channel(channel, state)

    def alarm_on(self) -> None:
        self.apply_pattern(self.config.alarm)

    def alarm_off(self) -> None:
        self.apply_pattern(self.config.idle)

    def close(self) -> None:
        try:
            if self._serial.is_open:
                self._serial.close()
        except Exception:
            logger.exception("Failed to close YSL301 serial port")

    def __enter__(self) -> "Ysl301Light":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


class TermiosSerial:
    def __init__(self, port: str, baudrate: int) -> None:
        if termios is None:
            raise RuntimeError("termios is unavailable")
        import fcntl

        baud = BAUDRATES.get(int(baudrate))
        if baud is None:
            raise ValueError(f"Unsupported termios baudrate: {baudrate}")

        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
        attrs[3] = 0
        attrs[4] = baud
        attrs[5] = baud
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 5
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

    @property
    def is_open(self) -> bool:
        return self.fd is not None

    def reset_output_buffer(self) -> None:
        if self.fd is None:
            raise RuntimeError("serial port is closed")
        termios.tcflush(self.fd, termios.TCOFLUSH)

    def write(self, data: bytes) -> int:
        if self.fd is None:
            raise RuntimeError("serial port is closed")
        total = 0
        view = memoryview(data)
        while total < len(data):
            written = os.write(self.fd, view[total:])
            if written <= 0:
                raise RuntimeError("serial write returned no data")
            total += written
        return total

    def flush(self) -> None:
        if self.fd is None:
            raise RuntimeError("serial port is closed")
        termios.tcdrain(self.fd)

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
