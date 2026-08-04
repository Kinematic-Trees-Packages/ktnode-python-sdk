"""High-level Python SDK for KT Robotics runtime nodes."""

from __future__ import annotations

import ctypes
import json
from dataclasses import dataclass
from enum import IntEnum
from . import abi


class NextStep(IntEnum):
    CONTINUE = abi.KT_ALGORITHM_CONTINUE
    STOP = abi.KT_ALGORITHM_STOP
    RECOVERABLE = abi.KT_ALGORITHM_RECOVERABLE
    FATAL = abi.KT_ALGORITHM_FATAL


class KtError(RuntimeError):
    pass


@dataclass(frozen=True)
class Message:
    payload: bytes
    source_id: str | None = None
    remote_time_ns: int | None = None


class Context:
    def __init__(self, lib: ctypes.CDLL, ptr: ctypes.POINTER(abi.KtAlgorithmContext)) -> None:
        self._lib = lib
        self._ptr = ptr

    def is_closing(self) -> bool:
        out = ctypes.c_uint32(0)
        _check_status(self._lib, self._lib.kt_context_is_closing(self._ptr, ctypes.byref(out)))
        return bool(out.value)

    def request_close(self) -> None:
        _check_status(self._lib, self._lib.kt_context_request_close(self._ptr))

    def report_error(self, message: str) -> None:
        view, keepalive = abi.string_view(message)
        _ = keepalive
        _check_status(self._lib, self._lib.kt_context_report_error(self._ptr, view))

    def set(self, channel: str, payload: bytes | bytearray | memoryview) -> None:
        channel_view, channel_keepalive = abi.string_view(channel)
        payload_view, payload_keepalive = abi.bytes_view(payload)
        error = ctypes.POINTER(abi.KtError)()
        status = self._lib.kt_context_set(self._ptr, channel_view, payload_view, ctypes.byref(error))
        _ = (channel_keepalive, payload_keepalive)
        _check_status(self._lib, status, error)

    def set_from(self, channel: str, source_id: str, payload: bytes | bytearray | memoryview) -> None:
        channel_view, channel_keepalive = abi.string_view(channel)
        source_view, source_keepalive = abi.string_view(source_id)
        payload_view, payload_keepalive = abi.bytes_view(payload)
        error = ctypes.POINTER(abi.KtError)()
        status = self._lib.kt_context_set_source(self._ptr, channel_view, source_view, payload_view, ctypes.byref(error))
        _ = (channel_keepalive, source_keepalive, payload_keepalive)
        _check_status(self._lib, status, error)


    def metrics_json(self) -> bytes:
        output = ctypes.POINTER(abi.KtOwnedBytes)()
        error = ctypes.POINTER(abi.KtError)()
        status = self._lib.kt_context_metrics_json(self._ptr, ctypes.byref(output), ctypes.byref(error))
        _check_status(self._lib, status, error)
        if not output:
            return b""
        try:
            return abi.view_to_bytes(self._lib.kt_owned_bytes_view(output))
        finally:
            self._lib.kt_owned_bytes_destroy(ctypes.byref(output))

    def metrics(self) -> dict[str, object]:
        payload = self.metrics_json()
        return json.loads(payload.decode("utf-8")) if payload else {}

    def get(self, channel: str, mode: int = abi.KT_READ_ONE, count: int = 0) -> list[Message]:
        channel_view, channel_keepalive = abi.string_view(channel)
        options = abi.KtReadOptionsV1(
            ctypes.sizeof(abi.KtReadOptionsV1),
            abi.KT_ABI_VERSION_MAJOR,
            mode,
            0,
            count,
            (ctypes.c_uint64 * 4)(),
        )
        batch = ctypes.POINTER(abi.KtMessageBatch)()
        error = ctypes.POINTER(abi.KtError)()
        status = self._lib.kt_context_read(self._ptr, channel_view, ctypes.byref(options), ctypes.byref(batch), ctypes.byref(error))
        _ = channel_keepalive
        _check_status(self._lib, status, error)
        if not batch:
            return []
        try:
            total = self._lib.kt_message_batch_count(batch)
            messages: list[Message] = []
            for index in range(total):
                item = abi.KtMessageViewV1()
                item.struct_size = ctypes.sizeof(abi.KtMessageViewV1)
                item.abi_version = abi.KT_ABI_VERSION_MAJOR
                item_error = ctypes.POINTER(abi.KtError)()
                item_status = self._lib.kt_message_batch_item(batch, index, ctypes.byref(item), ctypes.byref(item_error))
                _check_status(self._lib, item_status, item_error)
                messages.append(
                    Message(
                        payload=abi.view_to_bytes(item.payload),
                        source_id=abi.view_to_str(item.source_id) if item.has_source else None,
                        remote_time_ns=int(item.remote_time_ns) if item.has_remote_time else None,
                    )
                )
            return messages
        finally:
            self._lib.kt_message_batch_destroy(ctypes.byref(batch))


class Node:
    def setup(self, ctx: Context) -> NextStep:
        return NextStep.CONTINUE

    def step(self, ctx: Context) -> NextStep:
        return NextStep.STOP

    def close(self, ctx: Context) -> NextStep:
        return NextStep.STOP


class Runtime:
    def __init__(self, package_path: str, runtime_path: str, node: Node, library_path: str | None = None) -> None:
        self._lib = abi.load_library(library_path)
        if self._lib.kt_abi_version_major() != abi.KT_ABI_VERSION_MAJOR:
            raise KtError(
                f"unsupported KT Robotics ABI major {self._lib.kt_abi_version_major()}, "
                f"expected {abi.KT_ABI_VERSION_MAJOR}"
            )
        self._node = node
        self._runtime = ctypes.POINTER(abi.KtRuntime)()
        self._user_data = ctypes.py_object(self)
        self._user_data_ptr = ctypes.cast(ctypes.pointer(self._user_data), ctypes.c_void_p)
        self._setup_cb = abi.KtAlgorithmSetupFn(_setup_trampoline)
        self._step_cb = abi.KtAlgorithmStepFn(_step_trampoline)
        self._close_cb = abi.KtAlgorithmCloseFn(_close_trampoline)
        self._callbacks = abi.KtAlgorithmCallbacksV1(
            ctypes.sizeof(abi.KtAlgorithmCallbacksV1),
            abi.KT_ABI_VERSION_MAJOR,
            self._setup_cb,
            self._step_cb,
            self._close_cb,
            (ctypes.c_uint64 * 4)(),
        )
        package_view, self._package_keepalive = abi.string_view(package_path)
        runtime_view, self._runtime_keepalive = abi.string_view(runtime_path)
        options = abi.KtRuntimeOptionsV1(
            ctypes.sizeof(abi.KtRuntimeOptionsV1),
            abi.KT_ABI_VERSION_MAJOR,
            package_view,
            runtime_view,
            ctypes.pointer(self._callbacks),
            self._user_data_ptr,
            (ctypes.c_uint64 * 4)(),
        )
        error = ctypes.POINTER(abi.KtError)()
        status = self._lib.kt_runtime_create_v1(ctypes.byref(options), ctypes.byref(self._runtime), ctypes.byref(error))
        _check_status(self._lib, status, error)

    def run(self) -> None:
        error = ctypes.POINTER(abi.KtError)()
        _check_status(self._lib, self._lib.kt_runtime_run(self._runtime, ctypes.byref(error)), error)

    def request_close(self) -> None:
        _check_status(self._lib, self._lib.kt_runtime_request_close(self._runtime))

    def destroy(self) -> None:
        if self._runtime:
            error = ctypes.POINTER(abi.KtError)()
            _check_status(self._lib, self._lib.kt_runtime_destroy(ctypes.byref(self._runtime), ctypes.byref(error)), error)

    def __enter__(self) -> "Runtime":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.destroy()

    def _invoke(self, method: str, ctx_ptr: ctypes.POINTER(abi.KtAlgorithmContext)) -> int:
        ctx = Context(self._lib, ctx_ptr)
        try:
            result = getattr(self._node, method)(ctx)
            return int(result)
        except Exception as exc:  # callbacks must not raise across C ABI
            try:
                ctx.report_error(f"Python node {method} failed: {exc}")
            except Exception:
                pass
            return int(NextStep.FATAL)


def run(package_path: str, runtime_path: str, node: Node, library_path: str | None = None) -> None:
    with Runtime(package_path, runtime_path, node, library_path=library_path) as runtime:
        runtime.run()


def _runtime_from_user_data(user_data: ctypes.c_void_p) -> Runtime:
    return ctypes.cast(user_data, ctypes.POINTER(ctypes.py_object)).contents.value


def _setup_trampoline(user_data: ctypes.c_void_p, ctx: ctypes.POINTER(abi.KtAlgorithmContext)) -> int:
    return _runtime_from_user_data(user_data)._invoke("setup", ctx)


def _step_trampoline(user_data: ctypes.c_void_p, ctx: ctypes.POINTER(abi.KtAlgorithmContext)) -> int:
    return _runtime_from_user_data(user_data)._invoke("step", ctx)


def _close_trampoline(user_data: ctypes.c_void_p, ctx: ctypes.POINTER(abi.KtAlgorithmContext)) -> int:
    return _runtime_from_user_data(user_data)._invoke("close", ctx)


def _check_status(lib: ctypes.CDLL, status: int, error: ctypes.POINTER(abi.KtError) | None = None) -> None:
    if status == abi.KT_STATUS_OK:
        return
    message = ""
    if error:
        try:
            message = abi.view_to_str(lib.kt_error_message(error))
        finally:
            lib.kt_error_destroy(ctypes.byref(error))
    if not message:
        message = abi.view_to_str(lib.kt_status_name(status)) or f"KT status {status}"
    raise KtError(message)
