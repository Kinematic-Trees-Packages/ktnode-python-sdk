#!/usr/bin/env python3
"""OpenCV-backed stress test for ktnode.vision helpers.

This is intentionally not a fake data generator. It reads real frames from a
video file with OpenCV, converts them to RGB, then asks the SDK helper to build
valid KT Node ImageSample messages.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

import cv2
from ktnode.vision import make_rgb_image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--frames", type=int, default=120, help="maximum frames to encode")
    parser.add_argument("--source", default="opencv-video-file")
    args = parser.parse_args()

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"could not open video: {args.video}")

    input_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    input_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    input_fps = cap.get(cv2.CAP_PROP_FPS)
    input_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    encoded_frames = 0
    encoded_bytes = 0
    started = time.perf_counter()

    try:
        while encoded_frames < args.frames:
            ok, bgr = cap.get()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            message = make_rgb_image(
                rgb,
                source=args.source,
                frame_number=encoded_frames,
                captured_unix_ns=time.time_ns(),
            )
            payload = message.to_bytes()
            encoded_bytes += len(payload)
            encoded_frames += 1
    finally:
        cap.release()

    elapsed = time.perf_counter() - started
    fps = encoded_frames / elapsed if elapsed else 0.0
    mib = encoded_bytes / (1024 * 1024)
    mib_s = mib / elapsed if elapsed else 0.0

    print(f"video={args.video}")
    print(f"input_width={input_width}")
    print(f"input_height={input_height}")
    print(f"input_fps={input_fps:.3f}")
    print(f"input_frames={input_frames}")
    print(f"encoded_frames={encoded_frames}")
    print(f"encoded_mib={mib:.2f}")
    print(f"elapsed_s={elapsed:.3f}")
    print(f"encode_fps={fps:.2f}")
    print(f"encode_mib_per_s={mib_s:.2f}")
    if encoded_frames == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
