from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from .transport import AirLinkError, AirLinkTransport


CORE_FEATURE = 0
GIGAWIT_FEATURE = 24

COMMAND_FIRMWARE = 5
COMMAND_GET_LOCAL_NAME = 0
COMMAND_GET_CODECS = 6
COMMAND_SET_CODECS = 7
COMMAND_GET_PAIRING_STATUS = 10
COMMAND_GET_CONNECTED_STATUS = 12
COMMAND_GET_PAIRED_DEVICES = 14
COMMAND_GET_REMOTE_NAME = 15
COMMAND_CONNECT_DEVICE = 16
COMMAND_DISCONNECT_DEVICE = 17
COMMAND_PAIR_DEVICE = 18
COMMAND_GET_APTX_MODE = 64
COMMAND_SET_APTX_MODE = 65
COMMAND_GET_LDAC_MODE = 66
COMMAND_SET_LDAC_MODE = 67
COMMAND_GET_BRIGHTNESS = 82

APTX_MODE_VALUES = frozenset((2, 3, 19))
LDAC_MODE_VALUES = frozenset((0, 1, 2))
PAIRING_MODE_VALUES = frozenset((0, 1, 2))

CODECS = {
    "aptX": 3,
    "aptXLL": 5,
    "aptXHD": 6,
    "aptxAdaptive": 7,
    "ldac": 8,
}


@dataclass(slots=True)
class ReadError:
    code: str
    command: int
    message: str


@dataclass(slots=True)
class ConnectionStatus:
    connected: bool
    connected_headsets: int
    connected_le_devices: int


@dataclass(slots=True)
class PairedDevice:
    address: tuple[int, ...]
    connected: bool
    connect_type: int
    profiles: tuple[int, ...]
    name: str | None = None
    name_error: ReadError | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    address: tuple[int, ...]
    name: str | None


def _empty_errors() -> dict[str, ReadError | None]:
    return {
        "firmware": None,
        "local_name": None,
        "codecs": None,
        "aptx_mode": None,
        "ldac_mode": None,
        "pairing_status": None,
        "connection_status": None,
        "paired_devices": None,
        "brightness_raw": None,
    }


@dataclass(slots=True)
class AirLinkState:
    firmware: str | None = None
    local_name: str | None = None
    codecs: dict[str, bool] = field(
        default_factory=lambda: dict.fromkeys(CODECS, False)
    )
    aptx_mode: int | None = None
    ldac_mode: int | None = None
    pairing_status: int | None = None
    connection_status: ConnectionStatus | None = None
    paired_devices: list[PairedDevice] = field(default_factory=list)
    brightness_raw: int | None = None
    errors: dict[str, ReadError | None] = field(default_factory=_empty_errors)

    @classmethod
    def from_previous(cls, previous: AirLinkState | None) -> AirLinkState:
        if previous is None:
            return cls()
        return cls(
            firmware=previous.firmware,
            local_name=previous.local_name,
            codecs={**dict.fromkeys(CODECS, False), **previous.codecs},
            aptx_mode=previous.aptx_mode,
            ldac_mode=previous.ldac_mode,
            pairing_status=previous.pairing_status,
            connection_status=previous.connection_status,
            paired_devices=list(previous.paired_devices),
            brightness_raw=previous.brightness_raw,
            errors={**_empty_errors(), **previous.errors},
        )


def decode_text(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace").replace("\0", "").strip()


def encode_name(name: str, max_bytes: int = 32) -> bytes:
    encoded = bytearray()
    for character in name:
        character_bytes = character.encode("utf-8")
        if len(encoded) + len(character_bytes) > max_bytes:
            break
        encoded.extend(character_bytes)
    return bytes(encoded)


def build_address_payload(address: tuple[int, ...] | list[int]) -> bytes:
    if len(address) != 6:
        raise ValueError("Bluetooth address must contain exactly six bytes")
    return bytes((0, *address, 0))


def _invalid_response(message: str, command: int | None = None) -> AirLinkError:
    return AirLinkError(message, "AIR_LINK_INVALID_RESPONSE", command=command)


def _require_payload(payload: bytes, minimum: int, label: str) -> bytes:
    if len(payload) < minimum:
        raise _invalid_response(
            f"{label} response is too short: expected {minimum}, received {len(payload)}"
        )
    return payload


def parse_codec_payload(payload: bytes | bytearray | list[int]) -> dict[str, bool]:
    raw = _require_payload(bytes(payload), 1, "codec")
    return {name: codec_id in raw for name, codec_id in CODECS.items()}


def build_codec_set_payload(codecs: dict[str, bool]) -> bytes:
    enabled = [codec_id for name, codec_id in CODECS.items() if codecs.get(name)]
    return bytes((*enabled, 1, 0))


def parse_connection_status(
    payload: bytes | bytearray | list[int],
) -> ConnectionStatus:
    raw = _require_payload(bytes(payload), 3, "connection status")
    return ConnectionStatus(raw[0] == 1, raw[1], raw[2])


def parse_paired_devices(
    payload: bytes | bytearray | list[int],
) -> list[PairedDevice]:
    raw = _require_payload(bytes(payload), 1, "paired devices")
    count = raw[0]
    _require_payload(raw, 1 + count * 12, "paired devices")
    devices = []
    for index in range(count):
        item = raw[index * 12 + 1 : index * 12 + 13]
        profiles = tuple(item[8:12])
        if any(profiles):
            devices.append(
                PairedDevice(
                    address=tuple(item[1:7]),
                    connected=item[7] == 0x80,
                    connect_type=item[0],
                    profiles=profiles,
                )
            )
    return devices


def parse_discovered_device(
    payload: bytes | bytearray | list[int],
) -> DiscoveredDevice:
    raw = _require_payload(bytes(payload), 20, "discovered device")
    address = tuple(raw[9:15])
    name_length = int.from_bytes(raw[18:20], "little")
    name = None
    if name_length > 1:
        end = 20 + name_length - 1
        _require_payload(raw, end, "discovered device name")
        name = decode_text(raw[20:end]) or None
    return DiscoveredDevice(address=address, name=name)


def _read_error(error: Exception, command: int) -> ReadError:
    return ReadError(
        code=getattr(error, "code", "AIR_LINK_READ_FAILED"),
        command=command,
        message=str(error),
    )


def _is_disconnected(error: Exception) -> bool:
    return getattr(error, "code", None) == "AIR_LINK_DISCONNECTED"


T = TypeVar("T")


def _read_property(
    transport: AirLinkTransport,
    state: AirLinkState,
    key: str,
    feature: int,
    command: int,
    parser: Callable[[bytes], T],
) -> None:
    try:
        setattr(state, key, parser(transport.request(feature, command)))
        state.errors[key] = None
    except Exception as error:
        if _is_disconnected(error):
            raise
        state.errors[key] = _read_error(error, command)


def _parse_byte(payload: bytes, label: str) -> int:
    return _require_payload(payload, 1, label)[0]


def _read_paired_devices(transport: AirLinkTransport, state: AirLinkState) -> None:
    try:
        devices = parse_paired_devices(
            transport.request(GIGAWIT_FEATURE, COMMAND_GET_PAIRED_DEVICES)
        )
        previous = {item.address: item for item in state.paired_devices}
        for device in devices:
            old = previous.get(device.address)
            device.name = old.name if old else None
            try:
                payload = transport.request(
                    GIGAWIT_FEATURE,
                    COMMAND_GET_REMOTE_NAME,
                    build_address_payload(device.address),
                )
                device.name = decode_text(_require_payload(payload, 1, "remote name"))
            except Exception as error:
                if _is_disconnected(error):
                    raise
                device.name_error = _read_error(error, COMMAND_GET_REMOTE_NAME)
        state.paired_devices = devices
        state.errors["paired_devices"] = None
    except Exception as error:
        if _is_disconnected(error):
            raise
        state.errors["paired_devices"] = _read_error(
            error, COMMAND_GET_PAIRED_DEVICES
        )


def read_state(
    transport: AirLinkTransport, previous: AirLinkState | None = None
) -> AirLinkState:
    state = AirLinkState.from_previous(previous)
    _read_property(
        transport,
        state,
        "firmware",
        CORE_FEATURE,
        COMMAND_FIRMWARE,
        lambda payload: decode_text(_require_payload(payload, 1, "firmware")),
    )
    _read_property(
        transport,
        state,
        "local_name",
        GIGAWIT_FEATURE,
        COMMAND_GET_LOCAL_NAME,
        decode_text,
    )
    _read_property(
        transport,
        state,
        "codecs",
        GIGAWIT_FEATURE,
        COMMAND_GET_CODECS,
        parse_codec_payload,
    )

    if state.errors["codecs"] is None and state.codecs["aptxAdaptive"]:
        _read_property(
            transport,
            state,
            "aptx_mode",
            GIGAWIT_FEATURE,
            COMMAND_GET_APTX_MODE,
            lambda payload: _parse_byte(payload, "aptX mode"),
        )
    elif state.errors["codecs"] is None:
        state.aptx_mode = None
        state.errors["aptx_mode"] = None

    if state.errors["codecs"] is None and state.codecs["ldac"]:
        _read_property(
            transport,
            state,
            "ldac_mode",
            GIGAWIT_FEATURE,
            COMMAND_GET_LDAC_MODE,
            lambda payload: _parse_byte(payload, "LDAC mode"),
        )
    elif state.errors["codecs"] is None:
        state.ldac_mode = None
        state.errors["ldac_mode"] = None

    _read_property(
        transport,
        state,
        "pairing_status",
        GIGAWIT_FEATURE,
        COMMAND_GET_PAIRING_STATUS,
        lambda payload: _parse_byte(payload, "pairing status"),
    )
    _read_property(
        transport,
        state,
        "connection_status",
        GIGAWIT_FEATURE,
        COMMAND_GET_CONNECTED_STATUS,
        parse_connection_status,
    )
    _read_property(
        transport,
        state,
        "brightness_raw",
        GIGAWIT_FEATURE,
        COMMAND_GET_BRIGHTNESS,
        lambda payload: _parse_byte(payload, "brightness"),
    )
    _read_paired_devices(transport, state)
    return state


class AirLinkDevice:
    def __init__(self, transport: AirLinkTransport) -> None:
        self.transport = transport

    def read_state(self, previous: AirLinkState | None = None) -> AirLinkState:
        return read_state(self.transport, previous)

    def read_codecs(self) -> dict[str, bool]:
        return parse_codec_payload(
            self.transport.request(GIGAWIT_FEATURE, COMMAND_GET_CODECS)
        )

    def read_pairing_status(self) -> int:
        payload = self.transport.request(
            GIGAWIT_FEATURE, COMMAND_GET_PAIRING_STATUS
        )
        return _parse_byte(payload, "pairing status")

    def set_pairing_mode(self, mode: int) -> int:
        if (
            isinstance(mode, bool)
            or not isinstance(mode, int)
            or mode not in PAIRING_MODE_VALUES
        ):
            raise ValueError(f"Unsupported pairing mode: {mode}")
        self.transport.request(
            GIGAWIT_FEATURE, 11, bytes((mode,))
        )
        confirmed = self.read_pairing_status()
        if confirmed != mode:
            raise AirLinkError(
                "pairing mode readback does not match the requested value",
                "AIR_LINK_READBACK_MISMATCH",
                command=COMMAND_GET_PAIRING_STATUS,
            )
        return confirmed

    def start_manual_pairing(self) -> int:
        self.transport.request(GIGAWIT_FEATURE, 11, b"\x00")
        self.transport.request(GIGAWIT_FEATURE, 11, b"\x02")
        confirmed = self.read_pairing_status()
        if confirmed != 2:
            raise AirLinkError(
                "manual pairing mode did not start",
                "AIR_LINK_READBACK_MISMATCH",
                command=COMMAND_GET_PAIRING_STATUS,
            )
        return confirmed

    def stop_manual_pairing(self) -> int:
        self.transport.request(GIGAWIT_FEATURE, 11, b"\x01")
        confirmed = self.read_pairing_status()
        if confirmed != 1:
            raise AirLinkError(
                "manual pairing mode did not stop",
                "AIR_LINK_READBACK_MISMATCH",
                command=COMMAND_GET_PAIRING_STATUS,
            )
        return confirmed

    def read_connection_status(self) -> ConnectionStatus:
        return parse_connection_status(
            self.transport.request(
                GIGAWIT_FEATURE, COMMAND_GET_CONNECTED_STATUS
            )
        )

    def read_paired_devices(self) -> list[PairedDevice]:
        return parse_paired_devices(
            self.transport.request(
                GIGAWIT_FEATURE, COMMAND_GET_PAIRED_DEVICES
            )
        )

    def read_remote_name(self, address: tuple[int, ...]) -> str:
        payload = self.transport.request(
            GIGAWIT_FEATURE,
            COMMAND_GET_REMOTE_NAME,
            build_address_payload(address),
        )
        return decode_text(_require_payload(payload, 1, "remote name"))

    def set_codecs(self, codecs: dict[str, bool]) -> dict[str, bool]:
        expected = {name: bool(codecs.get(name)) for name in CODECS}
        self.transport.request(
            GIGAWIT_FEATURE,
            COMMAND_SET_CODECS,
            build_codec_set_payload(expected),
        )
        confirmed = self.read_codecs()
        if confirmed != expected:
            raise AirLinkError(
                "codec readback does not match the requested configuration",
                "AIR_LINK_READBACK_MISMATCH",
                command=COMMAND_GET_CODECS,
            )
        return confirmed

    def read_aptx_mode(self) -> int:
        payload = self.transport.request(GIGAWIT_FEATURE, COMMAND_GET_APTX_MODE)
        return _parse_byte(payload, "aptX mode")

    def set_aptx_mode(self, mode: int) -> int:
        if isinstance(mode, bool) or not isinstance(mode, int) or mode not in APTX_MODE_VALUES:
            raise ValueError(f"Unsupported aptX Adaptive mode: {mode}")
        self.transport.request(
            GIGAWIT_FEATURE, COMMAND_SET_APTX_MODE, bytes((mode,))
        )
        confirmed = self.read_aptx_mode()
        if confirmed != mode:
            raise AirLinkError(
                "aptX Adaptive mode readback does not match the requested value",
                "AIR_LINK_READBACK_MISMATCH",
                command=COMMAND_GET_APTX_MODE,
            )
        return confirmed

    def read_ldac_mode(self) -> int:
        payload = self.transport.request(GIGAWIT_FEATURE, COMMAND_GET_LDAC_MODE)
        return _parse_byte(payload, "LDAC mode")

    def set_ldac_mode(self, mode: int) -> int:
        if isinstance(mode, bool) or not isinstance(mode, int) or mode not in LDAC_MODE_VALUES:
            raise ValueError(f"Unsupported LDAC mode: {mode}")
        self.transport.request(
            GIGAWIT_FEATURE, COMMAND_SET_LDAC_MODE, bytes((mode,))
        )
        confirmed = self.read_ldac_mode()
        if confirmed != mode:
            raise AirLinkError(
                "LDAC mode readback does not match the requested value",
                "AIR_LINK_READBACK_MISMATCH",
                command=COMMAND_GET_LDAC_MODE,
            )
        return confirmed

    def connect_device(
        self,
        address: tuple[int, ...] | list[int],
        *,
        timeout_seconds: float = 20.0,
        poll_interval_seconds: float = 0.4,
    ) -> tuple[list[PairedDevice], ConnectionStatus]:
        return self._set_device_connected(
            address,
            True,
            COMMAND_CONNECT_DEVICE,
            timeout_seconds,
            poll_interval_seconds,
        )

    def disconnect_device(
        self,
        address: tuple[int, ...] | list[int],
        *,
        timeout_seconds: float = 12.0,
        poll_interval_seconds: float = 0.4,
    ) -> tuple[list[PairedDevice], ConnectionStatus]:
        return self._set_device_connected(
            address,
            False,
            COMMAND_DISCONNECT_DEVICE,
            timeout_seconds,
            poll_interval_seconds,
        )

    def begin_pair_device(
        self, address: tuple[int, ...] | list[int]
    ) -> None:
        self.transport.request(
            GIGAWIT_FEATURE,
            COMMAND_PAIR_DEVICE,
            build_address_payload(tuple(address)),
        )

    def _set_device_connected(
        self,
        address: tuple[int, ...] | list[int],
        expected: bool,
        action_command: int,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> tuple[list[PairedDevice], ConnectionStatus]:
        normalized_address = tuple(address)
        self.transport.request(
            GIGAWIT_FEATURE,
            action_command,
            build_address_payload(normalized_address),
        )
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        latest_devices: list[PairedDevice] = []
        latest_status: ConnectionStatus | None = None
        while True:
            latest_devices = self.read_paired_devices()
            latest_status = self.read_connection_status()
            target = next(
                (
                    device
                    for device in latest_devices
                    if device.address == normalized_address
                ),
                None,
            )
            if target is not None and target.connected == expected:
                return latest_devices, latest_status
            if time.monotonic() >= deadline:
                break
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)
        raise AirLinkError(
            "device connection readback does not match the requested state",
            "AIR_LINK_READBACK_MISMATCH",
            command=action_command,
        )

    def close(self) -> None:
        self.transport.close()
