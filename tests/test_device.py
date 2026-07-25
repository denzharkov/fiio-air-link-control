import unittest

from fiiocontrol.device import (
    AirLinkDevice,
    AirLinkState,
    ConnectionStatus,
    build_address_payload,
    build_codec_set_payload,
    parse_codec_payload,
    parse_connection_status,
    parse_discovered_device,
    parse_paired_devices,
    read_state,
)
from fiiocontrol.transport import AirLinkError


class ScriptedTransport:
    def __init__(
        self,
        responses: dict[int, bytes] | None = None,
        errors: dict[int, Exception] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.errors = errors or {}
        self.commands: list[int] = []
        self.payloads: list[bytes] = []

    def request(
        self,
        _feature: int,
        command: int,
        payload: bytes | bytearray | list[int] = b"",
        **_options: object,
    ) -> bytes:
        self.commands.append(command)
        self.payloads.append(bytes(payload))
        if command in self.errors:
            raise self.errors[command]
        return self.responses.get(command, b"")

    def close(self) -> None:
        pass


class SequenceTransport:
    def __init__(self, interactions: list[tuple[int, bytes]]) -> None:
        self.interactions = list(interactions)
        self.commands: list[int] = []
        self.payloads: list[bytes] = []

    def request(
        self,
        _feature: int,
        command: int,
        payload: bytes | bytearray | list[int] = b"",
        **_options: object,
    ) -> bytes:
        self.commands.append(command)
        self.payloads.append(bytes(payload))
        if not self.interactions:
            raise AssertionError(f"unexpected command {command}")
        expected, response = self.interactions.pop(0)
        if expected != command:
            raise AssertionError(f"expected command {expected}, received {command}")
        return response

    def close(self) -> None:
        pass


def transport_error(code: str, message: str) -> AirLinkError:
    return AirLinkError(message, code)


class DeviceParserTests(unittest.TestCase):
    def test_parses_codec_connection_address_and_devices(self) -> None:
        self.assertEqual(
            parse_codec_payload([3, 7, 8]),
            {
                "aptX": True,
                "aptXLL": False,
                "aptXHD": False,
                "aptxAdaptive": True,
                "ldac": True,
            },
        )
        self.assertEqual(
            build_codec_set_payload(
                {"aptX": True, "aptxAdaptive": True, "ldac": True}
            ),
            bytes((3, 7, 8, 1, 0)),
        )
        self.assertEqual(
            parse_connection_status([1, 2, 3]), ConnectionStatus(True, 2, 3)
        )
        self.assertEqual(
            build_address_payload([1, 2, 3, 4, 5, 6]),
            bytes((0, 1, 2, 3, 4, 5, 6, 0)),
        )
        with self.assertRaises(AirLinkError):
            parse_connection_status([1])
        with self.assertRaises(AirLinkError):
            parse_paired_devices([1, 2])

        devices = parse_paired_devices(
            [1, 2, 1, 2, 3, 4, 5, 6, 0x80, 1, 0, 0, 0]
        )
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].address, (1, 2, 3, 4, 5, 6))
        self.assertTrue(devices[0].connected)

    def test_requires_six_address_bytes(self) -> None:
        with self.assertRaises(ValueError):
            build_address_payload([1, 2])

    def test_parses_discovery_event_address_and_name(self) -> None:
        payload = bytearray(26)
        payload[9:15] = bytes((1, 2, 3, 4, 5, 6))
        payload[18:20] = (6).to_bytes(2, "little")
        payload[20:26] = b"Buds\0"

        device = parse_discovered_device(payload)

        self.assertEqual(device.address, (1, 2, 3, 4, 5, 6))
        self.assertEqual(device.name, "Buds")


class DeviceStateTests(unittest.TestCase):
    def test_isolates_get_errors_and_preserves_confirmed_value(self) -> None:
        transport = ScriptedTransport(
            {
                5: b"1.4.0",
                6: bytes((7, 8)),
                10: b"\x02",
                12: bytes((1, 1, 0)),
                14: b"\x00",
                64: b"\x13",
                66: b"\x00",
                82: b"\x07",
            },
            {0: transport_error("AIR_LINK_TIMEOUT", "name timed out")},
        )

        state = read_state(transport, AirLinkState(local_name="Previous name"))

        self.assertEqual(state.firmware, "1.4.0")
        self.assertEqual(state.local_name, "Previous name")
        self.assertEqual(state.errors["local_name"].code, "AIR_LINK_TIMEOUT")
        self.assertEqual(state.aptx_mode, 19)
        self.assertEqual(state.ldac_mode, 0)
        self.assertEqual(state.pairing_status, 2)
        self.assertEqual(state.connection_status, ConnectionStatus(True, 1, 0))
        self.assertEqual(state.brightness_raw, 7)
        self.assertEqual(transport.commands, [5, 0, 6, 64, 66, 10, 12, 82, 14])

    def test_skips_mode_reads_when_codecs_are_disabled(self) -> None:
        transport = ScriptedTransport(
            {
                5: b"1.4.0",
                0: b"A",
                6: b"\x03",
                10: b"\x00",
                12: b"\x00\x00\x00",
                14: b"\x00",
                82: b"\x07",
            }
        )
        state = read_state(transport)
        self.assertIsNone(state.aptx_mode)
        self.assertIsNone(state.ldac_mode)
        self.assertNotIn(64, transport.commands)
        self.assertNotIn(66, transport.commands)

    def test_keeps_device_when_remote_name_fails(self) -> None:
        transport = ScriptedTransport(
            {
                5: b"1.4.0",
                0: b"A",
                6: b"\x01\x00",
                10: b"\x00",
                12: b"\x00\x00\x00",
                14: bytes((1, 2, 1, 2, 3, 4, 5, 6, 0, 1, 0, 0, 0)),
                82: b"\x07",
            },
            {15: transport_error("AIR_LINK_TIMEOUT", "remote name timed out")},
        )
        previous = AirLinkState()
        previous.paired_devices = parse_paired_devices(
            [1, 2, 1, 2, 3, 4, 5, 6, 0, 1, 0, 0, 0]
        )
        previous.paired_devices[0].name = "Previous receiver"

        state = read_state(transport, previous)
        self.assertEqual(state.paired_devices[0].name, "Previous receiver")
        self.assertEqual(state.paired_devices[0].name_error.command, 15)
        self.assertIsNone(state.errors["paired_devices"])

    def test_propagates_disconnect(self) -> None:
        disconnected = transport_error("AIR_LINK_DISCONNECTED", "device removed")
        with self.assertRaises(AirLinkError) as caught:
            read_state(ScriptedTransport(errors={5: disconnected}))
        self.assertIs(caught.exception, disconnected)

    def test_verifies_codec_write_with_targeted_readback(self) -> None:
        confirmed_transport = ScriptedTransport({6: bytes((3, 7))})
        confirmed = AirLinkDevice(confirmed_transport).set_codecs(
            {"aptX": True, "aptxAdaptive": True}
        )
        self.assertTrue(confirmed["aptX"])
        self.assertTrue(confirmed["aptxAdaptive"])
        self.assertEqual(confirmed_transport.commands, [7, 6])
        self.assertEqual(
            confirmed_transport.payloads[0], bytes((3, 7, 1, 0))
        )

        mismatch = AirLinkDevice(ScriptedTransport({6: b"\x03"}))
        with self.assertRaises(AirLinkError) as caught:
            mismatch.set_codecs({"aptX": True, "aptxAdaptive": True})
        self.assertEqual(caught.exception.code, "AIR_LINK_READBACK_MISMATCH")
        self.assertEqual(caught.exception.command, 6)

    def test_sets_quality_modes_with_targeted_readback(self) -> None:
        aptx_transport = ScriptedTransport({64: b"\x13", 65: b""})
        aptx_device = AirLinkDevice(aptx_transport)
        self.assertEqual(aptx_device.set_aptx_mode(19), 19)
        self.assertEqual(aptx_transport.commands, [65, 64])
        self.assertEqual(aptx_transport.payloads[0], b"\x13")

        ldac_transport = ScriptedTransport({66: b"\x02", 67: b""})
        ldac_device = AirLinkDevice(ldac_transport)
        self.assertEqual(ldac_device.set_ldac_mode(2), 2)
        self.assertEqual(ldac_transport.commands, [67, 66])
        self.assertEqual(ldac_transport.payloads[0], b"\x02")

    def test_rejects_invalid_or_mismatched_quality_modes(self) -> None:
        device = AirLinkDevice(ScriptedTransport({64: b"\x02", 65: b""}))
        with self.assertRaises(ValueError):
            device.set_aptx_mode(4)
        with self.assertRaises(ValueError):
            device.set_ldac_mode(True)
        with self.assertRaises(AirLinkError) as caught:
            device.set_aptx_mode(19)
        self.assertEqual(caught.exception.code, "AIR_LINK_READBACK_MISMATCH")
        self.assertEqual(caught.exception.command, 64)

    def test_connects_and_disconnects_device_with_get_readback(self) -> None:
        address = (1, 2, 3, 4, 5, 6)
        connected_list = bytes((1, 2, *address, 0x80, 1, 0, 0, 0))
        disconnected_list = bytes((1, 2, *address, 0, 1, 0, 0, 0))

        connect_transport = SequenceTransport(
            [(16, b""), (14, connected_list), (12, b"\x01\x01\x00")]
        )
        devices, status = AirLinkDevice(connect_transport).connect_device(
            address, timeout_seconds=0, poll_interval_seconds=0
        )
        self.assertTrue(devices[0].connected)
        self.assertTrue(status.connected)
        self.assertEqual(connect_transport.commands, [16, 14, 12])
        self.assertEqual(
            connect_transport.payloads[0], bytes((0, *address, 0))
        )

        disconnect_transport = SequenceTransport(
            [(17, b""), (14, disconnected_list), (12, b"\x00\x00\x00")]
        )
        devices, status = AirLinkDevice(disconnect_transport).disconnect_device(
            address, timeout_seconds=0, poll_interval_seconds=0
        )
        self.assertFalse(devices[0].connected)
        self.assertFalse(status.connected)
        self.assertEqual(disconnect_transport.commands, [17, 14, 12])

    def test_does_not_retry_connection_action_after_readback_mismatch(self) -> None:
        address = (1, 2, 3, 4, 5, 6)
        disconnected_list = bytes((1, 2, *address, 0, 1, 0, 0, 0))
        transport = SequenceTransport(
            [(16, b""), (14, disconnected_list), (12, b"\x00\x00\x00")]
        )

        with self.assertRaises(AirLinkError) as caught:
            AirLinkDevice(transport).connect_device(
                address, timeout_seconds=-1, poll_interval_seconds=0
            )

        self.assertEqual(caught.exception.code, "AIR_LINK_READBACK_MISMATCH")
        self.assertEqual(transport.commands, [16, 14, 12])
        self.assertEqual(transport.commands.count(16), 1)

    def test_sets_pairing_mode_with_targeted_readback(self) -> None:
        transport = ScriptedTransport({10: b"\x02", 11: b""})
        device = AirLinkDevice(transport)

        self.assertEqual(device.set_pairing_mode(2), 2)
        self.assertEqual(transport.commands, [11, 10])
        self.assertEqual(transport.payloads[0], b"\x02")

        with self.assertRaises(ValueError):
            device.set_pairing_mode(3)

        mismatch = AirLinkDevice(ScriptedTransport({10: b"\x00", 11: b""}))
        with self.assertRaises(AirLinkError) as caught:
            mismatch.set_pairing_mode(2)
        self.assertEqual(caught.exception.code, "AIR_LINK_READBACK_MISMATCH")

    def test_starts_and_stops_manual_pairing_with_stable_modes(self) -> None:
        start_transport = ScriptedTransport({10: b"\x02", 11: b""})
        self.assertEqual(AirLinkDevice(start_transport).start_manual_pairing(), 2)
        self.assertEqual(start_transport.commands, [11, 11, 10])
        self.assertEqual(start_transport.payloads[:2], [b"\x00", b"\x02"])

        stop_transport = ScriptedTransport({10: b"\x01", 11: b""})
        self.assertEqual(AirLinkDevice(stop_transport).stop_manual_pairing(), 1)
        self.assertEqual(stop_transport.commands, [11, 10])
        self.assertEqual(stop_transport.payloads[0], b"\x01")

    def test_sends_pair_action_for_discovered_device(self) -> None:
        address = (1, 2, 3, 4, 5, 6)
        transport = SequenceTransport([(18, b"")])

        AirLinkDevice(transport).begin_pair_device(address)

        self.assertEqual(transport.commands, [18])
        self.assertEqual(transport.payloads[0], bytes((0, *address, 0)))


if __name__ == "__main__":
    unittest.main()
