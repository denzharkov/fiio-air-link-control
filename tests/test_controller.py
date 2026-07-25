import unittest
from unittest.mock import patch

from fiiocontrol.controller import AirLinkController
from fiiocontrol.device import AirLinkState
from fiiocontrol.hid_backend import HidDescriptor


DESCRIPTOR = HidDescriptor(
    path=b"control",
    product_string="FIIO Air Link",
    manufacturer_string="FIIO",
    serial_number=None,
    interface_number=1,
    usage_page=0xFF00,
    usage=3,
)


class FakeTransport:
    firmware = "1.4.0"
    instances: list["FakeTransport"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.requests: list[tuple[int, int, bytes]] = []
        self.timeout_seconds = 0.0
        self.post_command_delay_seconds = 0.0
        self.__class__.instances.append(self)

    def request(self, feature: int, command: int, payload: bytes = b"") -> bytes:
        self.requests.append((feature, command, payload))
        return self.firmware.encode() if command == 5 else b""

    def on_notification(self, _listener):
        return lambda: None


class FakeDevice:
    instances: list["FakeDevice"] = []

    def __init__(self, transport: FakeTransport) -> None:
        self.transport = transport
        self.pair_requests: list[tuple[int, ...]] = []
        self.__class__.instances.append(self)

    def read_state(self, state: AirLinkState) -> AirLinkState:
        return state

    def begin_pair_device(self, address: tuple[int, ...]) -> None:
        self.pair_requests.append(address)

    def close(self) -> None:
        pass


class ControllerSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeTransport.instances.clear()
        FakeDevice.instances.clear()

    def _connect(self, firmware: str) -> AirLinkController:
        FakeTransport.firmware = firmware
        patches = (
            patch("fiiocontrol.controller.enumerate_air_link", return_value=[DESCRIPTOR]),
            patch("fiiocontrol.controller.HidApiDevice", return_value=object()),
            patch("fiiocontrol.controller.AirLinkTransport", FakeTransport),
            patch("fiiocontrol.controller.AirLinkDevice", FakeDevice),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            controller = AirLinkController()
            controller.connect()
        return controller

    def test_unknown_firmware_runs_notification_handshake(self) -> None:
        self._connect("2.0.0")

        self.assertEqual(
            FakeTransport.instances[0].requests,
            [(0, 5, b""), (0, 8, b"\x18"), (0, 7, b"\x18")],
        )

    def test_confirmed_firmware_runs_notification_handshake(self) -> None:
        self._connect("1.4.0")

        self.assertEqual(
            FakeTransport.instances[0].requests,
            [(0, 5, b""), (0, 8, b"\x18"), (0, 7, b"\x18")],
        )

    def test_pair_action_is_available_on_unknown_firmware(self) -> None:
        controller = self._connect("2.0.0")
        address = (1, 2, 3, 4, 5, 6)

        controller.begin_pair_discovered_device(address)

        self.assertEqual(FakeDevice.instances[0].pair_requests, [address])


if __name__ == "__main__":
    unittest.main()
