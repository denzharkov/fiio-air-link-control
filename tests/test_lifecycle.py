import time
import unittest
from types import SimpleNamespace

from fiiocontrol.capabilities import capabilities_for_firmware
from fiiocontrol.controller import ConnectionSnapshot
from fiiocontrol.device import AirLinkState, PairedDevice
from fiiocontrol.hid_backend import HidDescriptor
from fiiocontrol.lifecycle import AirLinkLifecycle, ConnectionPhase


DESCRIPTOR = HidDescriptor(
    path=b"air-link-control",
    product_string="FIIO Air Link",
    manufacturer_string="FIIO",
    serial_number=None,
    interface_number=1,
    usage_page=0xFF00,
    usage=3,
)


class FakeController:
    def __init__(self) -> None:
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.state = AirLinkState(firmware="1.4.0")
        self.refresh_calls = 0
        self.notification_listeners = []
        self.pairing_modes: list[int] = []
        self.refresh_connection_calls = 0
        self.add_device_on_refresh = False
        self.pending_pair_address = None

    def connect(self) -> ConnectionSnapshot:
        self.connect_calls += 1
        return ConnectionSnapshot(
            "FIIO Air Link",
            self.state,
            DESCRIPTOR,
            capabilities_for_firmware(self.state.firmware),
        )

    def refresh(self) -> AirLinkState:
        self.refresh_calls += 1
        return self.state

    def set_codecs(self, codecs: dict[str, bool]) -> AirLinkState:
        self.state.codecs = codecs
        return self.state

    def set_aptx_mode(self, mode: int) -> AirLinkState:
        self.state.aptx_mode = mode
        return self.state

    def set_ldac_mode(self, mode: int) -> AirLinkState:
        self.state.ldac_mode = mode
        return self.state

    def connect_paired_device(self, _address: tuple[int, ...]) -> AirLinkState:
        self.state.connection_status = None
        return self.state

    def disconnect_paired_device(self, _address: tuple[int, ...]) -> AirLinkState:
        self.state.connection_status = None
        return self.state

    def set_pairing_mode(self, mode: int) -> AirLinkState:
        self.pairing_modes.append(mode)
        self.state.pairing_status = mode
        return self.state

    def start_manual_pairing(self) -> AirLinkState:
        self.pairing_modes.extend((0, 2))
        self.state.pairing_status = 2
        return self.state

    def stop_manual_pairing(self) -> AirLinkState:
        self.pairing_modes.append(1)
        self.state.pairing_status = 1
        return self.state

    def begin_pair_discovered_device(self, address: tuple[int, ...]) -> None:
        self.pending_pair_address = address

    def _add_pending_pair(self) -> None:
        address = self.pending_pair_address
        if address is not None and not any(
            item.address == address for item in self.state.paired_devices
        ):
            self.state.paired_devices.append(
                PairedDevice(
                    address=address,
                    connected=True,
                    connect_type=2,
                    profiles=(1, 0, 0, 0),
                    name="New receiver",
                )
            )
            self.pending_pair_address = None

    def refresh_connections(self) -> AirLinkState:
        self.refresh_connection_calls += 1
        self._add_pending_pair()
        if self.add_device_on_refresh and not self.state.paired_devices:
            self.state.paired_devices.append(
                PairedDevice(
                    address=(1, 2, 3, 4, 5, 6),
                    connected=False,
                    connect_type=2,
                    profiles=(1, 0, 0, 0),
                    name="New receiver",
                )
            )
        return self.state

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def on_notification(self, listener):
        self.notification_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self.notification_listeners:
                self.notification_listeners.remove(listener)

        return unsubscribe

    def emit_notification(self) -> None:
        for listener in tuple(self.notification_listeners):
            listener(SimpleNamespace(command=0x83, payload=b""))

    def emit_discovery(self, payload: bytes) -> None:
        for listener in tuple(self.notification_listeners):
            listener(SimpleNamespace(command=0x81, payload=payload))


class MutablePresence:
    def __init__(self, present: bool = False) -> None:
        self.present = present

    def __call__(self, path: bytes | None = None) -> bool:
        return self.present and (path is None or path == DESCRIPTOR.path)


def wait_for(predicate, timeout: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not met before timeout")
        time.sleep(0.005)


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = FakeController()
        self.presence = MutablePresence()
        self.lifecycle = AirLinkLifecycle(
            self.controller,
            presence_check=self.presence,
            poll_interval=0.01,
        )

    def tearDown(self) -> None:
        self.lifecycle.stop()

    def test_auto_connects_when_device_appears(self) -> None:
        self.lifecycle.start()
        self.assertEqual(self.lifecycle.snapshot().phase, ConnectionPhase.SEARCHING)

        self.presence.present = True
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)

        snapshot = self.lifecycle.snapshot()
        self.assertEqual(self.controller.connect_calls, 1)
        self.assertEqual(snapshot.connection.state.firmware, "1.4.0")
        self.assertTrue(snapshot.auto_connect)

    def test_reconnects_after_physical_disconnect(self) -> None:
        self.presence.present = True
        self.lifecycle.start()
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)

        self.presence.present = False
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.RECONNECTING)
        self.assertIsNone(self.lifecycle.snapshot().connection)

        self.presence.present = True
        wait_for(
            lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED
            and self.controller.connect_calls == 2
        )

    def test_manual_disconnect_pauses_auto_connect(self) -> None:
        self.presence.present = True
        self.lifecycle.start()
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)

        self.lifecycle.disconnect()
        time.sleep(0.04)

        snapshot = self.lifecycle.snapshot()
        self.assertEqual(snapshot.phase, ConnectionPhase.OFFLINE)
        self.assertFalse(snapshot.auto_connect)
        self.assertIsNone(snapshot.connection)
        self.assertEqual(self.controller.connect_calls, 1)

        self.lifecycle.connect()
        self.assertEqual(self.lifecycle.snapshot().phase, ConnectionPhase.CONNECTED)
        self.assertEqual(self.controller.connect_calls, 2)

    def test_refresh_transitions_through_synced_state(self) -> None:
        self.presence.present = True
        self.lifecycle.connect()
        previous_revision = self.lifecycle.revision

        snapshot = self.lifecycle.refresh()

        self.assertEqual(snapshot.phase, ConnectionPhase.CONNECTED)
        self.assertGreater(snapshot.revision, previous_revision)

    def test_updates_quality_mode_through_serialized_operation(self) -> None:
        self.presence.present = True
        self.lifecycle.connect()

        snapshot = self.lifecycle.set_ldac_mode(2)

        self.assertEqual(snapshot.phase, ConnectionPhase.CONNECTED)
        self.assertEqual(snapshot.connection.state.ldac_mode, 2)

    def test_runs_paired_device_action_through_serialized_operation(self) -> None:
        self.presence.present = True
        self.lifecycle.connect()

        snapshot = self.lifecycle.connect_paired_device((1, 2, 3, 4, 5, 6))

        self.assertEqual(snapshot.phase, ConnectionPhase.CONNECTED)

    def test_debounces_notification_into_background_refresh(self) -> None:
        self.presence.present = True
        self.lifecycle.start()
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)
        initial_refreshes = self.controller.refresh_calls

        self.controller.emit_notification()
        self.controller.emit_notification()
        wait_for(lambda: self.controller.refresh_calls > initial_refreshes)

        self.assertEqual(self.controller.refresh_calls, initial_refreshes + 1)

    def test_starts_and_stops_pairing_session(self) -> None:
        self.presence.present = True
        self.lifecycle.connect()

        started = self.lifecycle.start_pairing()
        self.assertTrue(started.pairing_active)
        self.assertEqual(self.controller.pairing_modes, [0, 2])

        stopped = self.lifecycle.stop_pairing()
        self.assertFalse(stopped.pairing_active)
        self.assertEqual(self.controller.pairing_modes, [0, 2, 1])

    def test_pairing_timeout_restores_stable_mode(self) -> None:
        self.lifecycle._pairing_timeout = 0.02
        self.presence.present = True
        self.lifecycle.start()
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)
        self.lifecycle.start_pairing()

        wait_for(lambda: not self.lifecycle.snapshot().pairing_active)

        self.assertEqual(self.controller.pairing_modes, [0, 2, 1])
        self.assertIn("истекло", self.lifecycle.snapshot().status)

    def test_pairing_poll_detects_new_device_and_stops(self) -> None:
        self.lifecycle._pairing_poll_interval = 0.01
        self.presence.present = True
        self.lifecycle.start()
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)
        self.lifecycle.start_pairing()
        self.controller.add_device_on_refresh = True

        wait_for(lambda: not self.lifecycle.snapshot().pairing_active)

        self.assertEqual(self.controller.pairing_modes, [0, 2, 1])
        self.assertEqual(
            self.lifecycle.snapshot().connection.state.paired_devices[0].name,
            "New receiver",
        )

    def test_discovery_event_can_be_selected_for_pairing(self) -> None:
        self.lifecycle._pairing_poll_interval = 0.01
        self.presence.present = True
        self.lifecycle.start()
        wait_for(lambda: self.lifecycle.snapshot().phase == ConnectionPhase.CONNECTED)
        self.lifecycle.start_pairing()
        payload = bytearray(26)
        payload[9:15] = bytes((1, 2, 3, 4, 5, 6))
        payload[18:20] = (6).to_bytes(2, "little")
        payload[20:26] = b"Buds\0"

        self.controller.emit_discovery(bytes(payload))
        discovered = self.lifecycle.snapshot().discovered_devices
        self.assertEqual(discovered[0].name, "Buds")

        self.lifecycle.pair_discovered_device(discovered[0].address)
        wait_for(lambda: not self.lifecycle.snapshot().pairing_active)
        paired = self.lifecycle.snapshot()
        self.assertEqual(
            paired.connection.state.paired_devices[0].address,
            discovered[0].address,
        )


if __name__ == "__main__":
    unittest.main()
