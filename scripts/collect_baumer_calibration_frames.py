from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from app.Cam.capture_backends import BaumerNeoApiCapture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect representative Baumer frames for INT8 calibration."
    )
    parser.add_argument("--output", default="/home/baumer/calibration_frames")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--pixel-format", default="BGR8")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    capture = BaumerNeoApiCapture(
        width=args.width,
        height=args.height,
        fps=args.fps,
        pixel_format=args.pixel_format,
    )
    if not capture.open():
        raise RuntimeError(capture.last_error or "Baumer camera open failed")

    saved = 0
    try:
        while saved < args.count:
            ok, frame = capture.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            path = output_dir / f"calib_{saved:05d}.jpg"
            cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            saved += 1
            time.sleep(max(0.0, args.interval))
    finally:
        capture.release()

    print(f"Saved {saved} calibration frames to {output_dir}")


if __name__ == "__main__":
    main()
