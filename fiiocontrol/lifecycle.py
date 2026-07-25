from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Callable

from .controller import AirLinkController, ConnectionSnapshot
from .diagnostics import AirLinkDiagnostics
from .device import AirLinkState, DiscoveredDevice, parse_discovered_device
from .hid_backend import is_air_link_present


class ConnectionPhase(StrEnum):
    OFFLINE = "offline"
    SEARCHING = "searching"
    CONNECTING = "connecting"
    SYNCHRONIZING = "synchronizing"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    phase: ConnectionPhase
    connection: ConnectionSnapshot | None
    status: str
    status_tone: str
    auto_connect: bool
    pairing_active: bool
    pairing_target: tuple[int, ...] | None
    discovered_devices: tuple[DiscoveredDevice, ...]
    revision: int


class AirLinkLifecycle:
    def __init__(
        self,
        controller: AirLinkController | None = None,
        *,
        presence_check: Callable[[bytes | None], bool] = is_air_link_present,
        poll_interval: float = 0.75,
        diagnostics: AirLinkDiagnostics | None = None,
        pairing_timeout: float = 60.0,
        pairing_poll_interval: float = 2.0,
    ) -> None:
        self.diagnostics = (
            diagnostics
            or getattr(controller, "diagnostics", None)
            or AirLinkDiagnostics(
                debug=os.environ.get("FIIO_AIR_LINK_DEBUG") == "1"
            )
        )
        self._controller = controller or AirLinkController(self.diagnostics)
        self._presence_check = presence_check
        self._poll_interval = poll_interval
        self._pairing_timeout = pairing_timeout
        self._pairing_poll_interval = pairing_poll_interval
        self._state_lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._notification_event = threading.Event()
        self._watcher: threading.Thread | None = None
        self._phase = ConnectionPhase.OFFLINE
        self._connection: ConnectionSnapshot | None = None
        self._status = "offline"
        self._status_tone = "muted"
        self._auto_connect = True
        self._pairing_active = False
        self._pairing_deadline = 0.0
        self._next_pairing_poll = 0.0
        self._pairing_known_addresses: frozenset[tuple[int, ...]] = frozenset()
        self._discovered_devices: dict[tuple[int, ...], DiscoveredDevice] = {}
        self._discovery_seen_at: dict[tuple[int, ...], float] = {}
        self._pairing_target: tuple[int, ...] | None = None
        self._pairing_attempt_deadline = 0.0
        self._revision = 0
        self._logger = logging.getLogger(__name__)
        subscribe = getattr(self._controller, "on_notification", None)
        self._unsubscribe_notification = (
            subscribe(self._handle_notification)
            if subscribe is not None
            else None
        )

    def start(self) -> None:
        with self._state_lock:
            if self._watcher is not None and self._watcher.is_alive():
                return
            self._stop_event.clear()
            self._set_state(
                phase=ConnectionPhase.SEARCHING,
                status="Ожидание FIIO Air Link...",
                status_tone="muted",
            )
            self._watcher = threading.Thread(
                target=self._watch,
                daemon=True,
                name="air-link-lifecycle",
            )
            self._watcher.start()

    def stop(self) -> None:
        self._stop_event.set()
        watcher = self._watcher
        if watcher is not None and watcher is not threading.current_thread():
            watcher.join(timeout=max(1.0, self._poll_interval * 2))
        with self._operation_lock:
            try:
                if self.snapshot().pairing_active:
                    self._controller.stop_manual_pairing()
            finally:
                self._controller.disconnect()
        with self._state_lock:
            self._watcher = None
            self._connection = None
            self._auto_connect = False
            self._clear_pairing()
            self._set_state(
                phase=ConnectionPhase.OFFLINE,
                status="offline",
                status_tone="muted",
            )
        if self._unsubscribe_notification is not None:
            self._unsubscribe_notification()
            self._unsubscribe_notification = None

    def snapshot(self) -> LifecycleSnapshot:
        with self._state_lock:
            return LifecycleSnapshot(
                phase=self._phase,
                connection=self._connection,
                status=self._status,
                status_tone=self._status_tone,
                auto_connect=self._auto_connect,
                pairing_active=self._pairing_active,
                pairing_target=self._pairing_target,
                discovered_devices=tuple(self._discovered_devices.values()),
                revision=self._revision,
            )

    @property
    def revision(self) -> int:
        with self._state_lock:
            return self._revision

    def connect(self) -> LifecycleSnapshot:
        with self._state_lock:
            self._auto_connect = True
        self._perform_connect(blocking=True)
        return self.snapshot()

    def disconnect(self) -> LifecycleSnapshot:
        with self._operation_lock:
            try:
                if self.snapshot().pairing_active:
                    self._controller.stop_manual_pairing()
            finally:
                self._controller.disconnect()
            with self._state_lock:
                self._connection = None
                self._auto_connect = False
                self._clear_pairing()
                self._set_state(
                    phase=ConnectionPhase.OFFLINE,
                    status="Отключено пользователем",
                    status_tone="muted",
                )
        return self.snapshot()

    def refresh(self) -> LifecycleSnapshot:
        with self._operation_lock:
            self._require_connection()
            self._set_state(
                phase=ConnectionPhase.SYNCHRONIZING,
                status="Air Link: чтение состояния...",
                status_tone="muted",
            )
            try:
                state = self._controller.refresh()
                self._replace_state(state)
                self._set_synced(state)
            except Exception as error:
                self._handle_operation_error(error)
        return self.snapshot()

    def set_codecs(self, codecs: dict[str, bool]) -> LifecycleSnapshot:
        with self._operation_lock:
            self._require_connection()
            self._set_state(
                phase=ConnectionPhase.SYNCHRONIZING,
                status="Air Link: запись кодеков...",
                status_tone="muted",
            )
            try:
                state = self._controller.set_codecs(codecs)
                self._replace_state(state)
                self._set_synced(state)
            except Exception as error:
                self._handle_operation_error(error)
        return self.snapshot()

    def set_aptx_mode(self, mode: int) -> LifecycleSnapshot:
        return self._set_quality_mode("aptX Adaptive", mode, self._controller.set_aptx_mode)

    def set_ldac_mode(self, mode: int) -> LifecycleSnapshot:
        return self._set_quality_mode("LDAC", mode, self._controller.set_ldac_mode)

    def connect_paired_device(self, address: tuple[int, ...]) -> LifecycleSnapshot:
        return self._set_device_connection(
            "подключение", address, self._controller.connect_paired_device
        )

    def disconnect_paired_device(self, address: tuple[int, ...]) -> LifecycleSnapshot:
        return self._set_device_connection(
            "отключение", address, self._controller.disconnect_paired_device
        )

    def start_pairing(self) -> LifecycleSnapshot:
        with self._operation_lock:
            connection = self._require_connection()
            self._set_state(
                phase=ConnectionPhase.SYNCHRONIZING,
                status="Air Link: запуск сопряжения...",
                status_tone="muted",
            )
            try:
                state = self._controller.start_manual_pairing()
                self._replace_state(state)
                now = time.monotonic()
                with self._state_lock:
                    self._pairing_active = True
                    self._pairing_deadline = now + self._pairing_timeout
                    self._next_pairing_poll = now
                    self._pairing_known_addresses = frozenset(
                        item.address for item in connection.state.paired_devices
                    )
                    self._discovered_devices.clear()
                    self._revision += 1
                self._set_state(
                    phase=ConnectionPhase.CONNECTED,
                    status="Сопряжение запущено. Включите pairing на новом устройстве.",
                    status_tone="warning",
                )
            except Exception as error:
                self._handle_operation_error(error)
        return self.snapshot()

    def stop_pairing(self) -> LifecycleSnapshot:
        with self._operation_lock:
            self._stop_pairing_locked("Сопряжение остановлено", "muted")
        return self.snapshot()

    def pair_discovered_device(
        self, address: tuple[int, ...]
    ) -> LifecycleSnapshot:
        with self._operation_lock:
            snapshot = self.snapshot()
            if not snapshot.pairing_active:
                self._set_state(
                    phase=snapshot.phase,
                    status="Сначала запустите сопряжение",
                    status_tone="error",
                )
                return self.snapshot()
            with self._state_lock:
                discovered = self._discovered_devices.get(address)
                last_seen = self._discovery_seen_at.get(address, 0.0)
            if discovered is None:
                self._set_state(
                    phase=snapshot.phase,
                    status="Обнаруженное устройство больше недоступно",
                    status_tone="error",
                )
                return self.snapshot()
            now = time.monotonic()
            if now - last_seen > 15.0:
                with self._state_lock:
                    self._discovered_devices.pop(address, None)
                    self._discovery_seen_at.pop(address, None)
                    self._revision += 1
                self._set_state(
                    phase=snapshot.phase,
                    status="Устройство больше не доступно. Запустите pairing повторно.",
                    status_tone="error",
                )
                return self.snapshot()
            self._set_state(
                phase=ConnectionPhase.CONNECTED,
                status=f"Сопряжение с {discovered.name or 'устройством'}...",
                status_tone="muted",
            )
            try:
                self._controller.begin_pair_discovered_device(address)
                with self._state_lock:
                    self._pairing_target = address
                    self._pairing_attempt_deadline = now + 15.0
                    self._pairing_deadline = now + self._pairing_timeout
                    self._next_pairing_poll = now
                    self._revision += 1
            except Exception as error:
                self._handle_operation_error(error)
        return self.snapshot()

    def set_status(self, status: str, tone: str = "muted") -> LifecycleSnapshot:
        snapshot = self.snapshot()
        self._set_state(
            phase=snapshot.phase,
            status=status,
            status_tone=tone,
        )
        return self.snapshot()

    def _set_quality_mode(
        self,
        label: str,
        mode: int,
        setter: Callable[[int], AirLinkState],
    ) -> LifecycleSnapshot:
        with self._operation_lock:
            self._require_connection()
            self._set_state(
                phase=ConnectionPhase.SYNCHRONIZING,
                status=f"Air Link: запись режима {label}...",
                status_tone="muted",
            )
            try:
                state = setter(mode)
                self._replace_state(state)
                self._set_synced(state)
            except Exception as error:
                self._handle_operation_error(error)
        return self.snapshot()

    def _set_device_connection(
        self,
        label: str,
        address: tuple[int, ...],
        setter: Callable[[tuple[int, ...]], AirLinkState],
    ) -> LifecycleSnapshot:
        with self._operation_lock:
            self._require_connection()
            self._set_state(
                phase=ConnectionPhase.SYNCHRONIZING,
                status=f"Air Link: {label} устройства...",
                status_tone="muted",
            )
            try:
                state = setter(address)
                self._replace_state(state)
                self._set_synced(state)
            except Exception as error:
                self._handle_operation_error(error)
        return self.snapshot()

    def _watch(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            if self._notification_event.is_set():
                self._refresh_after_notification()
            snapshot = self.snapshot()
            try:
                path = (
                    snapshot.connection.descriptor.path
                    if snapshot.connection and snapshot.connection.descriptor
                    else None
                )
                present = self._presence_check(path)
            except Exception as error:
                self._logger.exception("Failed to enumerate Air Link HID interfaces")
                self._set_state(
                    phase=ConnectionPhase.ERROR,
                    status=f"Ошибка обнаружения HID: {error}",
                    status_tone="error",
                )
                continue

            if snapshot.connection is not None and not present:
                self._handle_physical_disconnect()
                continue
            if snapshot.connection is not None and snapshot.pairing_active:
                self._poll_pairing_session()
            if (
                snapshot.connection is None
                and snapshot.auto_connect
                and present
                and snapshot.phase
                not in {ConnectionPhase.CONNECTING, ConnectionPhase.SYNCHRONIZING}
            ):
                self._perform_connect(blocking=False)

    def _poll_pairing_session(self) -> None:
        now = time.monotonic()
        with self._state_lock:
            if not self._pairing_active:
                return
            expired = now >= self._pairing_deadline
            should_poll = now >= self._next_pairing_poll
        if not expired and not should_poll:
            return
        if not self._operation_lock.acquire(blocking=False):
            return
        try:
            if expired:
                self._stop_pairing_locked(
                    "Время сопряжения истекло", "warning"
                )
                return
            with self._state_lock:
                self._next_pairing_poll = now + self._pairing_poll_interval
                known = self._pairing_known_addresses
                target = self._pairing_target
                attempt_expired = (
                    target is not None and now >= self._pairing_attempt_deadline
                )
                stale = [
                    address
                    for address, seen_at in self._discovery_seen_at.items()
                    if now - seen_at > 15.0 and address != target
                ]
                for address in stale:
                    self._discovery_seen_at.pop(address, None)
                    self._discovered_devices.pop(address, None)
                if stale:
                    self._revision += 1
            try:
                state = self._controller.refresh_connections()
                self._replace_state(state)
                current = frozenset(item.address for item in state.paired_devices)
                new_addresses = current - known
                if target is not None and target in current:
                    name = self._discovered_devices.get(target)
                    self._stop_pairing_locked(
                        f"{name.name if name and name.name else 'Новое устройство'} сопряжено",
                        "success",
                    )
                elif target is not None and attempt_expired:
                    with self._state_lock:
                        self._pairing_target = None
                        self._pairing_attempt_deadline = 0.0
                        self._discovered_devices.pop(target, None)
                        self._discovery_seen_at.pop(target, None)
                        self._revision += 1
                    self._set_state(
                        phase=ConnectionPhase.CONNECTED,
                        status="Сопряжение не выполнено. Снова включите pairing на наушниках.",
                        status_tone="error",
                    )
                elif target is None and new_addresses:
                    self._stop_pairing_locked("Новое устройство сопряжено", "success")
            except Exception as error:
                self._handle_operation_error(error)
        finally:
            self._operation_lock.release()

    def _stop_pairing_locked(self, status: str, tone: str) -> None:
        if not self.snapshot().pairing_active:
            return
        try:
            state = self._controller.stop_manual_pairing()
            self._replace_state(state)
            state = self._controller.refresh_connections()
            self._replace_state(state)
        except Exception as error:
            self._clear_pairing()
            self._handle_operation_error(error)
            return
        self._clear_pairing()
        self._set_state(
            phase=ConnectionPhase.CONNECTED,
            status=status,
            status_tone=tone,
        )

    def _refresh_after_notification(self) -> None:
        if not self._operation_lock.acquire(blocking=False):
            return
        try:
            self._notification_event.clear()
            if self.snapshot().connection is None:
                return
            try:
                state = self._controller.refresh()
                self._replace_state(state)
                self._set_synced(state)
            except Exception as error:
                self._handle_operation_error(error)
        finally:
            self._operation_lock.release()

    def _handle_notification(self, notification) -> None:
        if notification.command == 0x81:
            with self._state_lock:
                if not self._pairing_active:
                    return
            try:
                discovered = parse_discovered_device(notification.payload)
            except Exception:
                self._logger.exception("Failed to parse Air Link discovery event")
                return
            with self._state_lock:
                previous = self._discovered_devices.get(discovered.address)
                if previous is not None and previous.name and not discovered.name:
                    discovered = DiscoveredDevice(
                        address=discovered.address,
                        name=previous.name,
                    )
                self._discovered_devices[discovered.address] = discovered
                self._discovery_seen_at[discovered.address] = time.monotonic()
                self._revision += 1
            return
        self._notification_event.set()

    def _perform_connect(self, *, blocking: bool) -> None:
        if not self._operation_lock.acquire(blocking=blocking):
            return
        try:
            reconnecting = self.snapshot().phase == ConnectionPhase.RECONNECTING
            if reconnecting:
                self.diagnostics.increment("reconnect_attempt")
            self._set_state(
                phase=(
                    ConnectionPhase.RECONNECTING
                    if reconnecting
                    else ConnectionPhase.CONNECTING
                ),
                status=(
                    "Air Link: повторное подключение..."
                    if reconnecting
                    else "Air Link: подключение..."
                ),
                status_tone="muted",
            )
            try:
                connection = self._controller.connect()
                with self._state_lock:
                    self._connection = connection
                    self._clear_pairing()
                if reconnecting:
                    self.diagnostics.increment("reconnect_success")
                self._set_synced(connection.state)
            except Exception as error:
                self._controller.disconnect()
                with self._state_lock:
                    self._connection = None
                    waiting_phase = (
                        ConnectionPhase.RECONNECTING
                        if reconnecting and self._auto_connect
                        else ConnectionPhase.SEARCHING
                        if self._auto_connect
                        else ConnectionPhase.ERROR
                    )
                    self._set_state(
                        phase=waiting_phase,
                        status=f"Ожидание Air Link: {error}",
                        status_tone="error",
                    )
        finally:
            self._operation_lock.release()

    def _handle_physical_disconnect(self) -> None:
        if not self._operation_lock.acquire(blocking=False):
            return
        try:
            self.diagnostics.increment("disconnect")
            self._controller.disconnect()
            with self._state_lock:
                self._connection = None
                self._clear_pairing()
                self._set_state(
                    phase=ConnectionPhase.RECONNECTING,
                    status="Air Link отключён. Ожидание повторного подключения...",
                    status_tone="warning",
                )
        finally:
            self._operation_lock.release()

    def _handle_operation_error(self, error: Exception) -> None:
        disconnected = getattr(error, "code", "") == "AIR_LINK_DISCONNECTED"
        if disconnected:
            self.diagnostics.increment("disconnect")
            self._controller.disconnect()
            with self._state_lock:
                self._connection = None
                self._clear_pairing()
                self._set_state(
                    phase=ConnectionPhase.RECONNECTING,
                    status=f"Соединение потеряно: {error}",
                    status_tone="warning",
                )
            return
        self._set_state(
            phase=ConnectionPhase.CONNECTED,
            status=f"Ошибка: {error}",
            status_tone="error",
        )

    def _replace_state(self, state: AirLinkState) -> None:
        with self._state_lock:
            if self._connection is not None:
                self._connection = replace(self._connection, state=state)
                self._revision += 1

    def _clear_pairing(self) -> None:
        with self._state_lock:
            if (
                self._pairing_active
                or self._pairing_known_addresses
                or self._discovered_devices
                or self._pairing_target is not None
            ):
                self._pairing_active = False
                self._pairing_deadline = 0.0
                self._next_pairing_poll = 0.0
                self._pairing_known_addresses = frozenset()
                self._discovered_devices.clear()
                self._discovery_seen_at.clear()
                self._pairing_target = None
                self._pairing_attempt_deadline = 0.0
                self._revision += 1

    def _set_synced(self, state: AirLinkState) -> None:
        self._set_state(
            phase=ConnectionPhase.CONNECTED,
            status=(
                f"Air Link {state.firmware}"
                if state.firmware
                else "Air Link подключён, часть чтений завершилась ошибкой"
            ),
            status_tone="success" if state.firmware else "warning",
        )

    def _require_connection(self) -> ConnectionSnapshot:
        connection = self.snapshot().connection
        if connection is None:
            raise RuntimeError("Air Link не подключён")
        return connection

    def _set_state(
        self,
        *,
        phase: ConnectionPhase,
        status: str,
        status_tone: str,
    ) -> None:
        with self._state_lock:
            if (
                self._phase == phase
                and self._status == status
                and self._status_tone == status_tone
            ):
                return
            self._phase = phase
            self._status = status
            self._status_tone = status_tone
            self._revision += 1
