from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


HEADER_SIZE = 8


@dataclass(frozen=True, slots=True)
class AirLinkPacket:
    raw: bytes
    feature_byte: int
    command: int
    payload: bytes


def _as_bytes(data: bytes | bytearray | memoryview | Iterable[int]) -> bytes:
    return bytes(data)


def encode_packet(
    feature: int,
    command: int,
    payload: bytes | bytearray | memoryview | Iterable[int] = b"",
) -> bytes:
    if not isinstance(feature, int) or not 0 <= feature <= 0x7F:
        raise ValueError("Air Link feature must be an integer between 0 and 127")
    if not isinstance(command, int) or not 0 <= command <= 0xFF:
        raise ValueError("Air Link command must be an integer between 0 and 255")

    payload_bytes = _as_bytes(payload)
    if len(payload_bytes) > 0xFF:
        raise ValueError("Air Link payload cannot exceed 255 bytes")

    return bytes(
        (0xFF, 0x03, 0x00, len(payload_bytes), 0x00, 0x1D, feature << 1, command)
    ) + payload_bytes


def parse_packet(
    data: bytes | bytearray | memoryview | Iterable[int],
) -> AirLinkPacket | None:
    raw = _as_bytes(data)
    if len(raw) < HEADER_SIZE:
        return None
    if raw[:3] != b"\xff\x03\x00" or raw[4:6] != b"\x00\x1d":
        return None

    packet_size = HEADER_SIZE + raw[3]
    if len(raw) < packet_size:
        return None

    packet = raw[:packet_size]
    return AirLinkPacket(
        raw=packet,
        feature_byte=packet[6],
        command=packet[7],
        payload=packet[8:],
    )
