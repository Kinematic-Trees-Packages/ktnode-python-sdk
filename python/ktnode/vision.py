"""Vision message helpers.

These helpers are contract builders: they turn caller-owned image data into KT
KT Node vision messages. They do not generate fake camera data. Tests and
examples may generate their own sample arrays/bytes, then pass them here.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flatbuffers


DEFAULT_CHANNELS = 3


@dataclass(frozen=True)
class RGBImage:
    source: str
    frame_number: int
    width: int
    height: int
    data: bytes
    captured_unix_ns: int
    channels: int = DEFAULT_CHANNELS

    @property
    def data_shape(self) -> list[int]:
        return [self.height, self.width, self.channels]

    def to_bytes(self) -> bytes:
        return encode_image_sample(self)


def make_rgb_image(
    image: Any,
    *,
    source: str,
    frame_number: int,
    width: int | None = None,
    height: int | None = None,
    captured_unix_ns: int | None = None,
    color_order: str = "rgb",
) -> RGBImage:
    """Build a valid RGB ImageSample message object from caller-owned image data.

    `image` may be a numpy-like array with `.shape` and `.tobytes()`, or raw
    bytes/bytearray/memoryview when `width` and `height` are supplied.

    Required fields are explicit when they cannot be inferred safely:
    - `source`
    - `frame_number`
    - width/height for raw byte payloads
    """
    if not source:
        raise ValueError("source is required")
    if frame_number < 0:
        raise ValueError("frame_number must be non-negative")
    if color_order.lower() != "rgb":
        raise ValueError("make_rgb_image expects RGB data; convert BGR/OpenCV frames before calling or pass a future BGR helper")

    inferred_height: int | None = None
    inferred_width: int | None = None
    inferred_channels: int | None = None

    if hasattr(image, "shape") and hasattr(image, "tobytes"):
        shape = list(image.shape)
        if len(shape) != 3:
            raise ValueError("RGB image arrays must have shape [height, width, channels]")
        inferred_height, inferred_width, inferred_channels = int(shape[0]), int(shape[1]), int(shape[2])
        data = image.tobytes()
    else:
        data = bytes(image)

    final_width = int(width if width is not None else inferred_width or 0)
    final_height = int(height if height is not None else inferred_height or 0)
    final_channels = int(inferred_channels or DEFAULT_CHANNELS)

    if final_width <= 0 or final_height <= 0:
        raise ValueError("width and height are required and must be positive")
    if final_channels != DEFAULT_CHANNELS:
        raise ValueError("RGB images must have exactly 3 channels")
    if len(data) != final_width * final_height * final_channels:
        raise ValueError("RGB data length does not match width * height * 3")

    return RGBImage(
        source=source,
        frame_number=frame_number,
        width=final_width,
        height=final_height,
        channels=final_channels,
        data=bytes(data),
        captured_unix_ns=int(captured_unix_ns if captured_unix_ns is not None else time.time_ns()),
    )


def schema_paths() -> list[Path]:
    raw = os.environ.get("KT_NODE_SCHEMA_PATH", "")
    return [Path(item) for item in raw.split(os.pathsep) if item]


def vision_sample_schema() -> Path:
    for root in schema_paths():
        candidate = root / "vision" / "vision_sample.fbs"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("vision/vision_sample.fbs not found in KT_NODE_SCHEMA_PATH")


def encode_image_sample(image: RGBImage) -> bytes:
    """Encode an RGB image contract object as bow.data.ImageSample FlatBuffer bytes."""
    ImageSample, CompressionFormat, ImageType, MediaPipeline = _generated_modules()
    builder = flatbuffers.Builder(max(1024, len(image.data) + 256))
    source = builder.CreateString(image.source)
    data = builder.CreateByteVector(image.data)
    ImageSample.StartDataShapeVector(builder, len(image.data_shape))
    for value in reversed(image.data_shape):
        builder.PrependUint32(value)
    data_shape = builder.EndVector()

    ImageSample.Start(builder)
    ImageSample.AddSource(builder, source)
    ImageSample.AddData(builder, data)
    ImageSample.AddDataShape(builder, data_shape)
    ImageSample.AddCompression(builder, CompressionFormat.CompressionFormat.RAW)
    ImageSample.AddImageType(builder, ImageType.ImageType.RGB)
    ImageSample.AddFrameNumber(builder, image.frame_number)
    ImageSample.AddNewDataFlag(builder, True)
    ImageSample.AddPipeline(builder, MediaPipeline.MediaPipeline.OTHER)
    ImageSample.AddCapturedUnixNs(builder, image.captured_unix_ns)
    sample = ImageSample.End(builder)
    builder.Finish(sample, file_identifier=b"VSM1")
    return bytes(builder.Output())


def decode_image_sample_summary(payload: bytes) -> dict[str, Any]:
    """Decode core ImageSample fields used by conformance tests."""
    ImageSample, CompressionFormat, ImageType, MediaPipeline = _generated_modules()
    if not ImageSample.ImageSample.ImageSampleBufferHasIdentifier(payload, 0):
        raise ValueError("payload is not a VSM1 ImageSample buffer")
    sample = ImageSample.ImageSample.GetRootAs(payload, 0)
    return {
        "source": sample.Source().decode("utf-8") if sample.Source() else "",
        "frame_number": sample.FrameNumber(),
        "data_shape": [sample.DataShape(i) for i in range(sample.DataShapeLength())],
        "data_prefix": [sample.Data(i) for i in range(min(sample.DataLength(), 12))],
        "data_length": sample.DataLength(),
        "compression": sample.Compression(),
        "compression_raw": CompressionFormat.CompressionFormat.RAW,
        "image_type": sample.ImageType(),
        "image_type_rgb": ImageType.ImageType.RGB,
        "pipeline": sample.Pipeline(),
        "pipeline_other": MediaPipeline.MediaPipeline.OTHER,
        "captured_unix_ns": sample.CapturedUnixNs(),
    }


def _generated_modules():
    generated = Path(__file__).resolve().parent / "generated"
    generated_text = str(generated)
    if generated_text not in sys.path:
        sys.path.insert(0, generated_text)
    from bow.data import CompressionFormat, ImageSample, ImageType, MediaPipeline

    return ImageSample, CompressionFormat, ImageType, MediaPipeline
