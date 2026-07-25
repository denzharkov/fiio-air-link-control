from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from .diagnostics import AirLinkDiagnostics
from .protocol import AirLinkPacket, encode_packet, parse_packet


DEFAULT_OUTPUT_REPORT_ID = 7
DEFAULT_RESPONSE_REPORT_ID = 8
DEFAULT_INPUT_REPORT_IDS = frozenset((8, 9))
DEFAULT_TIMEOUT_SECONDS = 4.0
DEFAULT_POST_COMMAND_DELAY_SECONDS = 0.3
DEFAULT_OUTPUT_REPORT_SIZE = 446
DEFAULT_INPUT_REPORT_SIZE = 446
READER_POLL_MILLISECONDS = 100


class HidDevice(Protocol):
    def write(self, data: bytes) -> int: ...

    def read(self, size: int, timeout_ms: int) -> list[int] | bytes: ...

    def close(self) -> None: ...


class AirLinkError(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        *,
        command: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.command = command


@dataclass(frozen=True, slots=True)
class AirLinkNotification:
    report_id: int | None
    raw: bytes
    packet: AirLinkPacket | None

    @property
    def feature_byte(self) -> int | None:
        return self.packet.feature_byte if self.packet else None

    @property
    def command(self) -> int | None:
        return self.packet.command if self.packet else None

    @property
    def payload(self) -> bytes:
        return self.packet.payload if self.packet else self.raw


@dataclass(slots=True)
class _PendingRequest:
    feature_byte: int
    command: int
    event: threading.Event = field(default_factory=threading.Event)
    payload: bytes | None = None
    error: AirLinkError | None = None


class AirLinkTransport:
    """Serialized command transport with one background HID reader."""

    def __init__(
        self,
        device: HidDevice,
        *,
        output_report_id: int = DEFAULT_OUTPUT_REPORT_ID,
        response_report_id: int = DEFAULT_RESPONSE_REPORT_ID,
        input_report_ids: frozenset[int] = DEFAULT_INPUT_REPORT_IDS,
        output_report_size: int = DEFAULT_OUTPUT_REPORT_SIZE,
        input_report_size: int = DEFAULT_INPUT_REPORT_SIZE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        post_command_delay_seconds: float = DEFAULT_POST_COMMAND_DELAY_SECONDS,
        debug: bool = False,
        diagnostics: AirLinkDiagnostics | None = None,
    ) -> None:
        self._device = device
        self.output_report_id = output_report_id
        self.response_report_id = response_report_id
        self.input_report_ids = input_report_ids
        self.output_report_size = output_report_size
        self.input_report_size = input_report_size
        self.timeout_seconds = timeout_seconds
        self.post_command_delay_seconds = post_command_delay_seconds
        self.debug = debug
        self.diagnostics = diagnostics or AirLinkDiagnostics(debug=debug)
        self._command_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._reader_stop = threading.Event()
        self._disposed = False
        self._terminal_error: AirLinkError | None = None
        self._pending: _PendingRequest | None = None
        self._quarantined_responses: set[tuple[int, int]] = set()
        self._notification_listeners: set[
            Callable[[AirLinkNotification], None]
        ] = set()
        self._logger = logging.getLogger(__name__)
        self._reader = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="air-link-hid-reader",
        )
        self._reader.start()

    def request(
        self,
        feature: int,
        command: int,
        payload: bytes | bytearray | list[int] = b"",
        *,
        timeout_seconds: float | None = None,
        post_command_delay_seconds: float | None = None,
    ) -> bytes:
        packet = encode_packet(feature, command, payload)
        if len(packet) > self.output_report_size:
            raise ValueError(
                f"Air Link packet is {len(packet)} bytes, report limit is "
                f"{self.output_report_size}"
            )
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        delay = (
            self.post_command_delay_seconds
            if post_command_delay_seconds is None
            else post_command_delay_seconds
        )

        with self._command_lock:
            feature_byte = (feature << 1) | 1
            self._ensure_request_allowed(feature_byte, command)
            pending = _PendingRequest(feature_byte, command)
            with self._state_lock:
                self._pending = pending
            report = bytes((self.output_report_id,)) + packet.ljust(
                self.output_report_size, b"\0"
            )
            self.diagnostics.record_packet("request", self.output_report_id, packet)
            self._log_packet("OUT", packet)

            try:
                try:
                    written = self._device.write(report)
                except OSError as error:
                    raise self._io_error("send", command, error) from error
                if written != len(report):
                    self.diagnostics.increment("io_error")
                    raise AirLinkError(
                        f"incomplete Air Link report write for command {command}: "
                        f"{written} of {len(report)} bytes",
                        "AIR_LINK_SEND_FAILED",
                        command=command,
                    )

                timed_out = not pending.event.wait(max(0.0, timeout))
                if timed_out:
                    with self._state_lock:
                        timed_out = not pending.event.is_set()
                        if timed_out:
                            self._quarantined_responses.add(
                                (pending.feature_byte, pending.command)
                            )
                if timed_out:
                    self.diagnostics.increment("timeout")
                    raise AirLinkError(
                        f"timed out waiting for Air Link command {command}",
                        "AIR_LINK_TIMEOUT",
                        command=command,
                    )
                if pending.error is not None:
                    raise pending.error
                if pending.payload is None:
                    raise AirLinkError(
                        f"Air Link command {command} completed without a payload",
                        "AIR_LINK_INVALID_RESPONSE",
                        command=command,
                    )
                return pending.payload
            finally:
                with self._state_lock:
                    if self._pending is pending:
                        self._pending = None
                if delay > 0 and not self.disposed:
                    time.sleep(delay)

    def on_notification(
        self, listener: Callable[[AirLinkNotification], None]
    ) -> Callable[[], None]:
        with self._state_lock:
            self._notification_listeners.add(listener)

        def unsubscribe() -> None:
            with self._state_lock:
                self._notification_listeners.discard(listener)

        return unsubscribe

    @property
    def disposed(self) -> bool:
        with self._state_lock:
            return self._disposed

    def close(self) -> None:
        with self._state_lock:
            if self._disposed:
                return
            self._disposed = True
            self._reader_stop.set()
            self._notification_listeners.clear()
            pending = self._pending
            if pending is not None:
                pending.error = AirLinkError(
                    "Air Link transport is disconnected",
                    "AIR_LINK_DISCONNECTED",
                    command=pending.command,
                )
                pending.event.set()
        try:
            self._device.close()
        except OSError:
            pass
        if self._reader is not threading.current_thread():
            self._reader.join(timeout=1.0)

    def _reader_loop(self) -> None:
        while not self._reader_stop.is_set():
            try:
                raw = self._device.read(
                    self.input_report_size + 1,
                    READER_POLL_MILLISECONDS,
                )
            except OSError as error:
                if self.disposed:
                    return
                self.diagnostics.increment("io_error")
                terminal = AirLinkError(
                    f"failed to read Air Link input report: {error}",
                    "AIR_LINK_DISCONNECTED",
                )
                with self._state_lock:
                    self._terminal_error = terminal
                    pending = self._pending
                    if pending is not None:
                        pending.error = AirLinkError(
                            str(terminal),
                            terminal.code,
                            command=pending.command,
                        )
                        pending.event.set()
                return
            if not raw:
                continue
            self._route_input(bytes(raw))

    def _route_input(self, raw: bytes) -> None:
        report_id = raw[0] if raw and raw[0] in self.input_report_ids else None
        response = self._without_report_id(raw)
        parsed = parse_packet(response)

        if parsed is None:
            if report_id == 9:
                self.diagnostics.record_packet("notification", report_id, response)
                self._dispatch_notification(
                    AirLinkNotification(report_id, response, None)
                )
            else:
                self.diagnostics.record_packet("malformed", report_id, response)
            return

        self._log_packet("IN", parsed.raw)
        with self._state_lock:
            response_key = (parsed.feature_byte, parsed.command)
            quarantined = (
                report_id == self.response_report_id
                and response_key in self._quarantined_responses
            )
            if quarantined:
                self._quarantined_responses.discard(response_key)
            pending = self._pending
            matched = (
                report_id == self.response_report_id
                and not quarantined
                and pending is not None
                and parsed.feature_byte == pending.feature_byte
                and parsed.command == pending.command
            )
            if matched:
                pending.payload = parsed.payload
                pending.event.set()

        if matched:
            self.diagnostics.record_packet("response", report_id, parsed.raw, parsed)
            return
        self.diagnostics.record_packet("notification", report_id, parsed.raw, parsed)
        self._dispatch_notification(AirLinkNotification(report_id, parsed.raw, parsed))

    def _ensure_request_allowed(self, feature_byte: int, command: int) -> None:
        with self._state_lock:
            terminal_error = self._terminal_error
            disposed = self._disposed
            quarantined = (feature_byte, command) in self._quarantined_responses
        if terminal_error is not None:
            raise AirLinkError(
                str(terminal_error), terminal_error.code, command=command
            )
        if disposed:
            raise AirLinkError(
                "Air Link transport is disconnected",
                "AIR_LINK_DISCONNECTED",
                command=command,
            )
        if quarantined:
            raise AirLinkError(
                f"Air Link command {command} cannot be repeated until its late "
                "response is discarded or the device reconnects",
                "AIR_LINK_STALE_RESPONSE_RISK",
                command=command,
            )

    def _io_error(self, operation: str, command: int, error: OSError) -> AirLinkError:
        self.diagnostics.increment("io_error")
        return AirLinkError(
            f"failed to {operation} Air Link command {command}: {error}",
            "AIR_LINK_DISCONNECTED",
            command=command,
        )

    def _without_report_id(self, data: bytes) -> bytes:
        if data and data[0] in self.input_report_ids:
            return data[1:]
        return data

    def _dispatch_notification(self, notification: AirLinkNotification) -> None:
        with self._state_lock:
            listeners = tuple(self._notification_listeners)
        for listener in listeners:
            try:
                listener(notification)
            except Exception:
                self._logger.exception("Air Link notification listener failed")

    def _log_packet(self, direction: str, data: bytes) -> None:
        if not self.debug:
            return
        parsed = parse_packet(data)
        details = (
            f"feature={parsed.feature_byte} command={parsed.command} "
            f"length={len(parsed.payload)}"
            if parsed
            else f"length={len(data)}"
        )
        self._logger.debug("Air Link %s %s %s", direction, details, data.hex(" "))
