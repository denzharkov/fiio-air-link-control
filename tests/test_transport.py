import threading
import time
import unittest
from collections import deque

from fiiocontrol.protocol import encode_packet, parse_packet
from fiiocontrol.diagnostics import AirLinkDiagnostics
from fiiocontrol.transport import AirLinkError, AirLinkTransport


class FakeHidDevice:
    def __init__(self, responses: list[bytes] | None = None) -> None:
        self.responses = deque(responses or [])
        self.initial_responses_wait_for_write = bool(responses)
        self.writes: list[bytes] = []
        self.closed = False
        self.condition = threading.Condition()

    def write(self, data: bytes) -> int:
        with self.condition:
            self.writes.append(bytes(data))
            self.initial_responses_wait_for_write = False
            self.condition.notify_all()
            return len(data)

    def read(self, _size: int, timeout_ms: int) -> list[int]:
        deadline = time.monotonic() + timeout_ms / 1000
        with self.condition:
            while (
                (not self.responses or self.initial_responses_wait_for_write)
                and not self.closed
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self.condition.wait(remaining)
            return list(self.responses.popleft()) if self.responses else []

    def emit(self, response: bytes) -> None:
        with self.condition:
            self.initial_responses_wait_for_write = False
            self.responses.append(response)
            self.condition.notify_all()

    def close(self) -> None:
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class FailingHidDevice(FakeHidDevice):
    def write(self, _data: bytes) -> int:
        raise OSError("device was removed")


class ShortWriteHidDevice(FakeHidDevice):
    def write(self, data: bytes) -> int:
        super().write(data)
        return len(data) - 1


def response(feature: int, command: int, payload: bytes = b"") -> bytes:
    packet = bytearray(encode_packet(feature, command, payload))
    packet[6] |= 1
    return bytes((8,)) + packet


def event_response(feature: int, command: int, payload: bytes = b"") -> bytes:
    return bytes((9,)) + response(feature, command, payload)[1:]


class TransportTests(unittest.TestCase):
    def test_writes_padded_report_and_reads_payload(self) -> None:
        device = FakeHidDevice([response(24, 6, b"\x03\x08")])
        diagnostics = AirLinkDiagnostics()
        transport = AirLinkTransport(
            device,
            post_command_delay_seconds=0,
            diagnostics=diagnostics,
        )

        payload = transport.request(24, 6)

        self.assertEqual(payload, b"\x03\x08")
        self.assertEqual(len(device.writes), 1)
        self.assertEqual(len(device.writes[0]), 447)
        self.assertEqual(device.writes[0][0], 7)
        sent = parse_packet(device.writes[0][1:])
        self.assertIsNotNone(sent)
        assert sent is not None
        self.assertEqual(sent.command, 6)
        counters = diagnostics.snapshot()["counters"]
        self.assertEqual(counters["requests"], 1)
        self.assertEqual(counters["responses"], 1)

    def test_routes_unmatched_packets_as_notifications(self) -> None:
        device = FakeHidDevice(
            [response(24, 12, b"\x01"), response(24, 6, b"\x03")]
        )
        transport = AirLinkTransport(device, post_command_delay_seconds=0)
        notifications: list[int] = []
        unsubscribe = transport.on_notification(
            lambda packet: notifications.append(packet.command)
        )

        self.assertEqual(transport.request(24, 6), b"\x03")
        self.assertEqual(notifications, [12])
        unsubscribe()

    def test_serializes_requests_from_multiple_threads(self) -> None:
        device = FakeHidDevice()
        transport = AirLinkTransport(device, post_command_delay_seconds=0)
        results: dict[int, bytes] = {}

        first = threading.Thread(
            target=lambda: results.__setitem__(6, transport.request(24, 6))
        )
        second = threading.Thread(
            target=lambda: results.__setitem__(12, transport.request(24, 12))
        )
        first.start()
        time.sleep(0.01)
        second.start()
        time.sleep(0.01)
        self.assertEqual(len(device.writes), 1)

        device.emit(response(24, 6, b"\x03"))
        first.join(0.5)
        time.sleep(0.01)
        self.assertEqual(len(device.writes), 2)
        device.emit(response(24, 12, b"\x01\x01\x00"))
        second.join(0.5)

        self.assertEqual(results[6], b"\x03")
        self.assertEqual(results[12], b"\x01\x01\x00")

    def test_times_out_and_accepts_following_request(self) -> None:
        device = FakeHidDevice()
        transport = AirLinkTransport(
            device, timeout_seconds=0.01, post_command_delay_seconds=0
        )
        with self.assertRaises(AirLinkError) as caught:
            transport.request(24, 6)
        self.assertEqual(caught.exception.code, "AIR_LINK_TIMEOUT")

        result: list[bytes] = []
        request = threading.Thread(
            target=lambda: result.append(
                transport.request(24, 12, timeout_seconds=0.1)
            )
        )
        request.start()
        time.sleep(0.01)
        device.emit(response(24, 12, b"\x00\x00\x00"))
        request.join(0.5)
        self.assertEqual(result, [b"\x00\x00\x00"])

    def test_quarantines_same_command_after_timeout_until_late_response(self) -> None:
        device = FakeHidDevice()
        transport = AirLinkTransport(
            device, timeout_seconds=0.01, post_command_delay_seconds=0
        )
        with self.assertRaises(AirLinkError):
            transport.request(24, 6)

        with self.assertRaises(AirLinkError) as caught:
            transport.request(24, 6)
        self.assertEqual(caught.exception.code, "AIR_LINK_STALE_RESPONSE_RISK")

        device.emit(response(24, 6, b"\x03"))
        time.sleep(0.02)
        result: list[bytes] = []
        request = threading.Thread(
            target=lambda: result.append(
                transport.request(24, 6, timeout_seconds=0.1)
            )
        )
        request.start()
        time.sleep(0.01)
        device.emit(response(24, 6, b"\x08"))
        request.join(0.5)
        self.assertEqual(result, [b"\x08"])

    def test_report_nine_cannot_complete_request(self) -> None:
        device = FakeHidDevice(
            [event_response(24, 6, b"\x03"), response(24, 6, b"\x08")]
        )
        notifications = []
        transport = AirLinkTransport(device, post_command_delay_seconds=0)
        transport.on_notification(notifications.append)

        self.assertEqual(transport.request(24, 6), b"\x08")
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].report_id, 9)

    def test_rejects_short_hid_write(self) -> None:
        transport = AirLinkTransport(
            ShortWriteHidDevice(), post_command_delay_seconds=0
        )

        with self.assertRaises(AirLinkError) as caught:
            transport.request(24, 6)

        self.assertEqual(caught.exception.code, "AIR_LINK_SEND_FAILED")

    def test_close_rejects_future_requests(self) -> None:
        device = FakeHidDevice()
        transport = AirLinkTransport(device, post_command_delay_seconds=0)
        transport.close()
        transport.close()

        with self.assertRaises(AirLinkError) as caught:
            transport.request(24, 6)
        self.assertEqual(caught.exception.code, "AIR_LINK_DISCONNECTED")
        self.assertTrue(device.closed)

    def test_maps_hid_io_failure_to_disconnect(self) -> None:
        transport = AirLinkTransport(
            FailingHidDevice(), post_command_delay_seconds=0
        )
        with self.assertRaises(AirLinkError) as caught:
            transport.request(24, 6)
        self.assertEqual(caught.exception.code, "AIR_LINK_DISCONNECTED")

    def test_delivers_raw_report_nine_while_idle(self) -> None:
        device = FakeHidDevice()
        diagnostics = AirLinkDiagnostics(debug=True)
        transport = AirLinkTransport(device, diagnostics=diagnostics)
        notifications = []
        transport.on_notification(notifications.append)

        device.emit(bytes((9, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)))
        deadline = time.monotonic() + 0.5
        while not notifications and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].report_id, 9)
        self.assertIsNone(notifications[0].packet)
        self.assertEqual(notifications[0].payload, bytes(range(1, 12)))
        self.assertEqual(
            diagnostics.snapshot()["counters"]["notifications"], 1
        )
        transport.close()


if __name__ == "__main__":
    unittest.main()
