"""Low-level ctypes binding for the kt-node native library, libkt_node.

This module is intentionally private-ish: node authors should use
`ktrobotics.runtime`, not call these functions directly.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path

KT_ABI_VERSION_MAJOR = 1
KT_ABI_VERSION_MINOR = 1

KT_STATUS_OK = 0

KT_READ_ONE = 0
KT_READ_ALL_AVAILABLE = 1
KT_READ_COUNT = 2

KT_ALGORITHM_CONTINUE = 0
KT_ALGORITHM_STOP = 1
KT_ALGORITHM_RECOVERABLE = 2
KT_ALGORITHM_FATAL = 3


class KtAlgorithmContext(ctypes.Structure):
    pass


class KtError(ctypes.Structure):
    pass


class KtMessageBatch(ctypes.Structure):
    pass


class KtOwnedBytes(ctypes.Structure):
    pass


class KtRuntime(ctypes.Structure):
    pass


class KtStringView(ctypes.Structure):
    _fields_ = [("data", ctypes.c_char_p), ("length", ctypes.c_uint64)]


class KtBytesView(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_uint8)), ("length", ctypes.c_uint64)]


class KtReadOptionsV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("mode", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint32),
        ("count", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64 * 4),
    ]


class KtMessageViewV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("payload", KtBytesView),
        ("source_id", KtStringView),
        ("has_source", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint32),
        ("remote_time_ns", ctypes.c_int64),
        ("has_remote_time", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("reserved", ctypes.c_uint64 * 4),
    ]


KtAlgorithmSetupFn = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(KtAlgorithmContext))
KtAlgorithmStepFn = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(KtAlgorithmContext))
KtAlgorithmCloseFn = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(KtAlgorithmContext))


class KtAlgorithmCallbacksV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("setup", KtAlgorithmSetupFn),
        ("step", KtAlgorithmStepFn),
        ("close", KtAlgorithmCloseFn),
        ("reserved", ctypes.c_uint64 * 4),
    ]


class KtRuntimeOptionsV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("package_path", KtStringView),
        ("runtime_path", KtStringView),
        ("callbacks", ctypes.POINTER(KtAlgorithmCallbacksV1)),
        ("user_data", ctypes.c_void_p),
        ("reserved", ctypes.c_uint64 * 4),
    ]


class KtVersionV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("major", ctypes.c_uint32),
        ("minor", ctypes.c_uint32),
        ("patch", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 3),
    ]


class KtCapabilitiesV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("bits", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64 * 6),
    ]


def string_view(value: str | os.PathLike[str]) -> tuple[KtStringView, bytes]:
    encoded = os.fsdecode(value).encode("utf-8")
    return KtStringView(encoded, len(encoded)), encoded


def bytes_view(value: bytes | bytearray | memoryview) -> tuple[KtBytesView, ctypes.Array[ctypes.c_uint8]]:
    payload = bytes(value)
    buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
    return KtBytesView(buffer, len(payload)), buffer


def view_to_str(view: KtStringView) -> str:
    if not view.data or view.length == 0:
        return ""
    return ctypes.string_at(view.data, view.length).decode("utf-8", errors="replace")


def view_to_bytes(view: KtBytesView) -> bytes:
    if not view.data or view.length == 0:
        return b""
    return ctypes.string_at(view.data, view.length)


def find_library(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for variable in ("KT_NODE_LIB", "KT_ROBOTICS_LIB"):
        env = os.environ.get(variable)
        if env:
            return env
    for root in os.environ.get("KT_NODE_PACKAGE_ROOTS", os.environ.get("KT_ROBOTICS_PACKAGE_ROOTS", "")).split(os.pathsep):
        if not root:
            continue
        candidates = [
            Path(root) / "lib" / "libkt_node.so",
            Path(root) / "lib" / "libkt_node.so.1",
        ]
        candidates.extend(Path(root).glob("dist/libkt_node/*/*/lib/libkt_node.so"))
        candidates.extend(Path(root).glob("dist/libkt_node/*/*/lib/libkt_node.so.1"))
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    found = ctypes.util.find_library("kt_node") or ctypes.util.find_library("ktnode")
    if found:
        return found
    return "libkt_node.so"


def load_library(path: str | None = None) -> ctypes.CDLL:
    lib = ctypes.CDLL(find_library(path))

    lib.kt_abi_version_major.restype = ctypes.c_uint32
    lib.kt_abi_version_minor.restype = ctypes.c_uint32

    lib.kt_status_name.argtypes = [ctypes.c_uint32]
    lib.kt_status_name.restype = KtStringView

    lib.kt_error_code.argtypes = [ctypes.POINTER(KtError)]
    lib.kt_error_code.restype = ctypes.c_uint32
    lib.kt_error_message.argtypes = [ctypes.POINTER(KtError)]
    lib.kt_error_message.restype = KtStringView
    lib.kt_error_destroy.argtypes = [ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_error_destroy.restype = None

    lib.kt_context_is_closing.argtypes = [ctypes.POINTER(KtAlgorithmContext), ctypes.POINTER(ctypes.c_uint32)]
    lib.kt_context_is_closing.restype = ctypes.c_uint32
    lib.kt_context_report_error.argtypes = [ctypes.POINTER(KtAlgorithmContext), KtStringView]
    lib.kt_context_report_error.restype = ctypes.c_uint32
    lib.kt_context_request_close.argtypes = [ctypes.POINTER(KtAlgorithmContext)]
    lib.kt_context_request_close.restype = ctypes.c_uint32
    lib.kt_context_set.argtypes = [ctypes.POINTER(KtAlgorithmContext), KtStringView, KtBytesView, ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_context_set.restype = ctypes.c_uint32
    lib.kt_context_set_source.argtypes = [ctypes.POINTER(KtAlgorithmContext), KtStringView, KtStringView, KtBytesView, ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_context_set_source.restype = ctypes.c_uint32
    lib.kt_context_read.argtypes = [ctypes.POINTER(KtAlgorithmContext), KtStringView, ctypes.POINTER(KtReadOptionsV1), ctypes.POINTER(ctypes.POINTER(KtMessageBatch)), ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_context_read.restype = ctypes.c_uint32
    lib.kt_context_metrics_json.argtypes = [ctypes.POINTER(KtAlgorithmContext), ctypes.POINTER(ctypes.POINTER(KtOwnedBytes)), ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_context_metrics_json.restype = ctypes.c_uint32
    lib.kt_owned_bytes_view.argtypes = [ctypes.POINTER(KtOwnedBytes)]
    lib.kt_owned_bytes_view.restype = KtBytesView
    lib.kt_owned_bytes_destroy.argtypes = [ctypes.POINTER(ctypes.POINTER(KtOwnedBytes))]
    lib.kt_owned_bytes_destroy.restype = None

    lib.kt_message_batch_count.argtypes = [ctypes.POINTER(KtMessageBatch)]
    lib.kt_message_batch_count.restype = ctypes.c_uint64
    lib.kt_message_batch_item.argtypes = [ctypes.POINTER(KtMessageBatch), ctypes.c_uint64, ctypes.POINTER(KtMessageViewV1), ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_message_batch_item.restype = ctypes.c_uint32
    lib.kt_message_batch_destroy.argtypes = [ctypes.POINTER(ctypes.POINTER(KtMessageBatch))]
    lib.kt_message_batch_destroy.restype = None

    lib.kt_runtime_create_v1.argtypes = [ctypes.POINTER(KtRuntimeOptionsV1), ctypes.POINTER(ctypes.POINTER(KtRuntime)), ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_runtime_create_v1.restype = ctypes.c_uint32
    lib.kt_runtime_run.argtypes = [ctypes.POINTER(KtRuntime), ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_runtime_run.restype = ctypes.c_uint32
    lib.kt_runtime_destroy.argtypes = [ctypes.POINTER(ctypes.POINTER(KtRuntime)), ctypes.POINTER(ctypes.POINTER(KtError))]
    lib.kt_runtime_destroy.restype = ctypes.c_uint32
    lib.kt_runtime_request_close.argtypes = [ctypes.POINTER(KtRuntime)]
    lib.kt_runtime_request_close.restype = ctypes.c_uint32
    lib.kt_runtime_version.argtypes = [ctypes.POINTER(KtVersionV1)]
    lib.kt_runtime_version.restype = ctypes.c_uint32
    lib.kt_runtime_capabilities_v1.argtypes = [ctypes.POINTER(KtCapabilitiesV1)]
    lib.kt_runtime_capabilities_v1.restype = ctypes.c_uint32

    return lib
