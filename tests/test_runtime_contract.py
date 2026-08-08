import ctypes
import unittest

from ktnode import Node, NextStep
from ktnode import abi
from ktnode.runtime import KtError, _check_status


class FakeLib:
    def kt_status_name(self, status):
        payload = f"STATUS_{status}".encode("utf-8")
        self._last_status_name = payload
        return abi.KtStringView(payload, len(payload))

    def kt_error_message(self, error):
        payload = b"detailed error"
        self._last_error_message = payload
        return abi.KtStringView(payload, len(payload))

    def kt_error_destroy(self, error_ptr):
        self.destroyed = True


class RuntimeContractTests(unittest.TestCase):
    def test_string_view_keeps_utf8_bytes_and_length(self):
        view, keepalive = abi.string_view("video.rgb")
        self.assertEqual(view.length, len(keepalive))
        self.assertEqual(abi.view_to_str(view), "video.rgb")

    def test_bytes_view_copies_payload(self):
        source = bytearray(b"abc")
        view, _keepalive = abi.bytes_view(source)
        source[:] = b"zzz"
        self.assertEqual(abi.view_to_bytes(view), b"abc")

    def test_default_node_is_safe(self):
        node = Node()
        self.assertEqual(node.setup(None), NextStep.CONTINUE)
        self.assertEqual(node.step(None), NextStep.STOP)
        self.assertEqual(node.close(None), NextStep.STOP)

    def test_status_error_uses_status_name_without_error_object(self):
        with self.assertRaises(KtError) as raised:
            _check_status(FakeLib(), 123)
        self.assertIn("STATUS_123", str(raised.exception))

    def test_status_error_destroys_error_object(self):
        lib = FakeLib()
        error = ctypes.POINTER(abi.KtError)()
        with self.assertRaises(KtError) as raised:
            _check_status(lib, 123, error)
        self.assertIn("STATUS_123", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
