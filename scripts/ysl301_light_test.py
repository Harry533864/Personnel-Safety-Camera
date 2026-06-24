#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inference.python_tensorrt.ysl301 import (  # noqa: E402
    DEFAULT_ALARM_PATTERN,
    DEFAULT_IDLE_PATTERN,
    Ysl301Config,
    Ysl301Light,
    build_write_coil_frame,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Turn on/off a YSL101/YSL301 serial alarm light.")
    parser.add_argument("--port", default="auto", help="Serial port, for example /dev/ttyUSB0. Default: auto")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--address", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=5, help="How long to keep the alarm pattern on.")
    parser.add_argument("--red", default=DEFAULT_ALARM_PATTERN["red"])
    parser.add_argument("--yellow", default=DEFAULT_ALARM_PATTERN["yellow"])
    parser.add_argument("--green", default=DEFAULT_ALARM_PATTERN["green"])
    parser.add_argument("--buzzer", default=DEFAULT_ALARM_PATTERN["buzzer"])
    parser.add_argument("--off", action="store_true", help="Only send the all-off pattern.")
    parser.add_argument("--dry-run", action="store_true", help="Print Modbus frames without opening the serial port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    alarm = {
        "red": args.red,
        "yellow": args.yellow,
        "green": args.green,
        "buzzer": args.buzzer,
    }
    idle = dict(DEFAULT_IDLE_PATTERN)

    if args.dry_run:
        pattern = idle if args.off else alarm
        for channel, state in pattern.items():
            frame = build_write_coil_frame(args.address, channel, state)
            print(f"{channel}={state}: {frame.hex(' ')}")
        return 0

    config = Ysl301Config(
        enabled=True,
        port=args.port,
        baudrate=args.baudrate,
        address=args.address,
        alarm=alarm,
        idle=idle,
    )

    with Ysl301Light(config) as light:
        print(f"YSL301 serial port: {light.port}")
        if args.off:
            light.alarm_off()
            print("Sent all-off pattern.")
            return 0

        light.alarm_on()
        print(f"Alarm pattern on for {args.seconds:g}s.")
        if args.seconds > 0:
            time.sleep(args.seconds)
            light.alarm_off()
            print("Sent all-off pattern.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
