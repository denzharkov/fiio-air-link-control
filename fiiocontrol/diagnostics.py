from __future__ import annotations

import threading
from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .protocol import AirLinkPacket, parse_packet


@dataclass(frozen=True, slots=True)
class PacketRecord:
    timestamp: str
    category: str
    report_id: int | None
    feature_byte: int | None
    command: int | None
    payload_length: int
    raw: bytes


class AirLinkDiagnostics:
    def __init__(self, *, debug: bool = False, capacity: int = 250) -> None:
        self.debug = debug
        self.capacity = capacity
        self._lock = threading.RLock()
        self._counters: Counter[str] = Counter()
        self._records: deque[PacketRecord] = deque(maxlen=capacity)
        self._last_success_at: str | None = None

    def record_packet(
        self,
        category: str,
        report_id: int | None,
        raw: bytes,
        packet: AirLinkPacket | None = None,
    ) -> None:
        parsed = packet if packet is not None else parse_packet(raw)
        record = PacketRecord(
            timestamp=_timestamp(),
            category=category,
            report_id=report_id,
            feature_byte=parsed.feature_byte if parsed else None,
            command=parsed.command if parsed else None,
            payload_length=len(parsed.payload) if parsed else 0,
            raw=bytes(raw) if self.debug else b"",
        )
        with self._lock:
            self._counters[category] += 1
            if category == "response":
                self._last_success_at = record.timestamp
            if self.debug or category in {"malformed", "error"}:
                self._records.append(record)

    def increment(self, metric: str) -> None:
        with self._lock:
            self._counters[metric] += 1

    def snapshot(self, *, include_raw: bool | None = None) -> dict[str, Any]:
        show_raw = self.debug if include_raw is None else include_raw
        with self._lock:
            counters = dict(self._counters)
            records = list(self._records)
            last_success = self._last_success_at
        return {
            "debug": self.debug,
            "capacity": self.capacity,
            "last_success_at": last_success,
            "counters": {
                "requests": counters.get("request", 0),
                "responses": counters.get("response", 0),
                "notifications": counters.get("notification", 0),
                "malformed": counters.get("malformed", 0),
                "timeouts": counters.get("timeout", 0),
                "disconnects": counters.get("disconnect", 0),
                "reconnect_attempts": counters.get("reconnect_attempt", 0),
                "reconnect_successes": counters.get("reconnect_success", 0),
                "io_errors": counters.get("io_error", 0),
            },
            "records": [
                _record_dict(record, include_raw=show_raw, redact=False)
                for record in records
            ],
        }

    def export_snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
        snapshot = self.snapshot(include_raw=False)
        snapshot["records"] = [
            _record_dict(record, include_raw=True, redact=True) for record in records
        ]
        snapshot["privacy"] = (
            "All packet payload bytes are redacted. Raw payloads never leave the "
            "in-memory development buffer."
        )
        return snapshot


def _record_dict(
    record: PacketRecord, *, include_raw: bool, redact: bool
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "timestamp": record.timestamp,
        "category": record.category,
        "report_id": record.report_id,
        "feature_byte": record.feature_byte,
        "command": record.command,
        "payload_length": record.payload_length,
    }
    if include_raw:
        result["packet"] = _redacted_packet(record.raw) if redact else record.raw.hex(" ")
    return result


def _redacted_packet(raw: bytes) -> str:
    packet = parse_packet(raw)
    if packet is None:
        return " ".join("**" for _ in raw)
    header = packet.raw[:8].hex(" ")
    payload = " ".join("**" for _ in packet.payload)
    return f"{header} {payload}".strip()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
