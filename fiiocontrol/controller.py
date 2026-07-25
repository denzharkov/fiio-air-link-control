from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from .capabilities import AirLinkCapabilities, capabilities_for_firmware
from .diagnostics import AirLinkDiagnostics
from .device import (
    AirLinkDevice,
    AirLinkState,
    ReadError,
    CORE_FEATURE,
    COMMAND_FIRMWARE,
    decode_text,
)
from .hid_backend import HidApiDevice, HidDescriptor, enumerate_air_link
from .transport import AirLinkError, AirLinkNotification, AirLinkTransport


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
    product_name: str
    state: AirLinkState
    descriptor: HidDescriptor | None = None
    capabilities: AirLinkCapabilities = field(default_factory=AirLinkCapabilities)


class AirLinkController:
    def __init__(self, diagnostics: AirLinkDiagnostics | None = None) -> None:
        self._lock = threading.RLock()
        self._device: AirLinkDevice | None = None
        self._descriptor: HidDescriptor | None = None
        self._state: AirLinkState | None = None
        self._capabilities = AirLinkCapabilities()
        self._notification_lock = threading.Lock()
        self._notification_listeners: set[
            Callable[[AirLinkNotification], None]
        ] = set()
        self.diagnostics = diagnostics or AirLinkDiagnostics(
            debug=os.environ.get("FIIO_AIR_LINK_DEBUG") == "1"
        )

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._device is not None

    @property
    def state(self) -> AirLinkState | None:
        with self._lock:
            return self._state

    def connect(self) -> ConnectionSnapshot:
        with self._lock:
            self.disconnect()
            descriptors = enumerate_air_link()
            if not descriptors:
                raise AirLinkError(
                    "FIIO Air Link не найден. Подключите устройство по USB.",
                    "AIR_LINK_NOT_FOUND",
                )

            controls = [
                descriptor
                for descriptor in descriptors
                if descriptor.usage_page == 0xFF00 and descriptor.usage == 3
            ]
            if controls:
                descriptors = controls

            failures: list[str] = []
            for descriptor in descriptors:
                candidate: AirLinkDevice | None = None
                try:
                    handle = HidApiDevice(descriptor)
                    transport = AirLinkTransport(
                        handle,
                        timeout_seconds=1.2,
                        post_command_delay_seconds=0.0,
                        debug=os.environ.get("FIIO_AIR_LINK_DEBUG") == "1",
                        diagnostics=self.diagnostics,
                    )
                    candidate = AirLinkDevice(transport)
                    transport.on_notification(self._dispatch_notification)
                    firmware = decode_text(
                        transport.request(CORE_FEATURE, COMMAND_FIRMWARE)
                    )
                    if not firmware:
                        raise AirLinkError(
                            "firmware query returned an empty response",
                            "AIR_LINK_INVALID_RESPONSE",
                            command=COMMAND_FIRMWARE,
                        )

                    transport.timeout_seconds = 4.0
                    transport.post_command_delay_seconds = 0.3
                    transport.request(CORE_FEATURE, 8, b"\x18")
                    state = candidate.read_state(AirLinkState(firmware=firmware))
                    transport.request(CORE_FEATURE, 7, b"\x18")
                    self._device = candidate
                    self._descriptor = descriptor
                    self._state = state
                    self._capabilities = capabilities_for_firmware(state.firmware)
                    return ConnectionSnapshot(
                        descriptor.product_string or "FIIO Air Link",
                        state,
                        descriptor,
                        self._capabilities,
                    )
                except Exception as error:
                    failures.append(str(error))
                    if candidate is not None:
                        candidate.close()
                    logging.getLogger(__name__).debug(
                        "HID interface %r rejected: %s", descriptor.path, error
                    )

            detail = failures[-1] if failures else "подходящий HID-интерфейс отсутствует"
            raise AirLinkError(
                f"Не найден интерфейс Air Link с report ID 7: {detail}",
                "AIR_LINK_INTERFACE_NOT_FOUND",
            )

    def refresh(self) -> AirLinkState:
        with self._lock:
            device = self._require_device()
            self._state = device.read_state(self._state)
            return self._state

    def set_codecs(self, codecs: dict[str, bool]) -> AirLinkState:
        with self._lock:
            if not self._capabilities.write_codecs:
                raise AirLinkError(
                    "Запись кодеков не подтверждена для этой firmware",
                    "AIR_LINK_UNSUPPORTED",
                )
            device = self._require_device()
            confirmed = device.set_codecs(codecs)
            if self._state is None:
                self._state = AirLinkState()
            self._state.codecs = confirmed
            self._state.errors["codecs"] = None
            self._refresh_enabled_modes(device, self._state)
            return self._state

    def set_aptx_mode(self, mode: int) -> AirLinkState:
        with self._lock:
            if not self._capabilities.write_aptx_mode:
                raise AirLinkError(
                    "Запись режима aptX Adaptive не подтверждена для этой firmware",
                    "AIR_LINK_UNSUPPORTED",
                )
            if self._state is None or not self._state.codecs.get("aptxAdaptive"):
                raise AirLinkError(
                    "Сначала включите aptX Adaptive",
                    "AIR_LINK_CODEC_DISABLED",
                )
            confirmed = self._require_device().set_aptx_mode(mode)
            self._state.aptx_mode = confirmed
            self._state.errors["aptx_mode"] = None
            return self._state

    def set_ldac_mode(self, mode: int) -> AirLinkState:
        with self._lock:
            if not self._capabilities.write_ldac_mode:
                raise AirLinkError(
                    "Запись режима LDAC не подтверждена для этой firmware",
                    "AIR_LINK_UNSUPPORTED",
                )
            if self._state is None or not self._state.codecs.get("ldac"):
                raise AirLinkError(
                    "Сначала включите LDAC",
                    "AIR_LINK_CODEC_DISABLED",
                )
            confirmed = self._require_device().set_ldac_mode(mode)
            self._state.ldac_mode = confirmed
            self._state.errors["ldac_mode"] = None
            return self._state

    def connect_paired_device(self, address: tuple[int, ...]) -> AirLinkState:
        return self._set_paired_device_connected(address, True)

    def disconnect_paired_device(self, address: tuple[int, ...]) -> AirLinkState:
        return self._set_paired_device_connected(address, False)

    def set_pairing_mode(self, mode: int) -> AirLinkState:
        with self._lock:
            if not self._capabilities.pairing:
                raise AirLinkError(
                    "Режим сопряжения не подтверждён для этой firmware",
                    "AIR_LINK_UNSUPPORTED",
                )
            confirmed = self._require_device().set_pairing_mode(mode)
            if self._state is None:
                raise AirLinkError(
                    "Air Link state is unavailable", "AIR_LINK_DISCONNECTED"
                )
            self._state.pairing_status = confirmed
            self._state.errors["pairing_status"] = None
            return self._state

    def start_manual_pairing(self) -> AirLinkState:
        return self._set_manual_pairing(True)

    def stop_manual_pairing(self) -> AirLinkState:
        return self._set_manual_pairing(False)

    def begin_pair_discovered_device(self, address: tuple[int, ...]) -> None:
        with self._lock:
            if not self._capabilities.pairing:
                raise AirLinkError(
                    "Сопряжение не поддерживается",
                    "AIR_LINK_UNSUPPORTED",
                )
            self._require_device().begin_pair_device(address)

    def refresh_connections(self) -> AirLinkState:
        with self._lock:
            device = self._require_device()
            if self._state is None:
                raise AirLinkError(
                    "Air Link state is unavailable", "AIR_LINK_DISCONNECTED"
                )
            previous = {item.address: item for item in self._state.paired_devices}
            devices = device.read_paired_devices()
            status = device.read_connection_status()
            self._merge_device_names(device, devices, previous)
            self._state.paired_devices = devices
            self._state.connection_status = status
            self._state.errors["paired_devices"] = None
            self._state.errors["connection_status"] = None
            return self._state

    def _set_manual_pairing(self, active: bool) -> AirLinkState:
        with self._lock:
            if not self._capabilities.pairing:
                raise AirLinkError(
                    "Режим сопряжения не подтверждён для этой firmware",
                    "AIR_LINK_UNSUPPORTED",
                )
            device = self._require_device()
            confirmed = (
                device.start_manual_pairing()
                if active
                else device.stop_manual_pairing()
            )
            if self._state is None:
                raise AirLinkError(
                    "Air Link state is unavailable", "AIR_LINK_DISCONNECTED"
                )
            self._state.pairing_status = confirmed
            self._state.errors["pairing_status"] = None
            return self._state

    def disconnect(self) -> None:
        with self._lock:
            if self._device is not None:
                self._device.close()
            self._device = None
            self._descriptor = None
            self._state = None
            self._capabilities = AirLinkCapabilities()

    def on_notification(
        self, listener: Callable[[AirLinkNotification], None]
    ) -> Callable[[], None]:
        with self._notification_lock:
            self._notification_listeners.add(listener)

        def unsubscribe() -> None:
            with self._notification_lock:
                self._notification_listeners.discard(listener)

        return unsubscribe

    def _require_device(self) -> AirLinkDevice:
        if self._device is None:
            raise AirLinkError(
                "Air Link не подключён", "AIR_LINK_DISCONNECTED"
            )
        return self._device

    def _set_paired_device_connected(
        self, address: tuple[int, ...], expected: bool
    ) -> AirLinkState:
        with self._lock:
            if not self._capabilities.manage_connections:
                raise AirLinkError(
                    "Управление подключениями не подтверждено для этой firmware",
                    "AIR_LINK_UNSUPPORTED",
                )
            if self._state is None:
                self._require_device()
                raise AssertionError("connected controller has no state")
            previous = {item.address: item for item in self._state.paired_devices}
            target = previous.get(address)
            if target is None:
                raise AirLinkError(
                    "Сопряжённое устройство не найдено",
                    "AIR_LINK_DEVICE_NOT_FOUND",
                )
            if target.connected == expected:
                return self._state
            device = self._require_device()
            if expected:
                devices, status = device.connect_device(address)
            else:
                devices, status = device.disconnect_device(address)
            self._merge_device_names(device, devices, previous)
            self._state.paired_devices = devices
            self._state.connection_status = status
            self._state.errors["paired_devices"] = None
            self._state.errors["connection_status"] = None
            return self._state

    @staticmethod
    def _merge_device_names(
        device: AirLinkDevice,
        devices: list,
        previous: dict,
    ) -> None:
        for item in devices:
            old = previous.get(item.address)
            if old is not None and old.name:
                item.name = old.name
                item.name_error = old.name_error
                continue
            try:
                item.name = device.read_remote_name(item.address)
                item.name_error = None
            except Exception as error:
                if getattr(error, "code", None) == "AIR_LINK_DISCONNECTED":
                    raise
                item.name = old.name if old else None
                item.name_error = ReadError(
                    code=getattr(error, "code", "AIR_LINK_READ_FAILED"),
                    command=15,
                    message=str(error),
                )

    @staticmethod
    def _refresh_enabled_modes(device: AirLinkDevice, state: AirLinkState) -> None:
        for codec, key, command, reader in (
            ("aptxAdaptive", "aptx_mode", 64, device.read_aptx_mode),
            ("ldac", "ldac_mode", 66, device.read_ldac_mode),
        ):
            if not state.codecs.get(codec):
                setattr(state, key, None)
                state.errors[key] = None
                continue
            try:
                setattr(state, key, reader())
                state.errors[key] = None
            except Exception as error:
                if getattr(error, "code", None) == "AIR_LINK_DISCONNECTED":
                    raise
                state.errors[key] = ReadError(
                    code=getattr(error, "code", "AIR_LINK_READ_FAILED"),
                    command=command,
                    message=str(error),
                )

    def _dispatch_notification(self, notification: AirLinkNotification) -> None:
        with self._notification_lock:
            listeners = tuple(self._notification_listeners)
        for listener in listeners:
            try:
                listener(notification)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Air Link controller notification listener failed"
                )
