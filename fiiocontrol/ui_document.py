from __future__ import annotations

from typing import Any

from .build_info import BuildInfo
from .controller import ConnectionSnapshot
from .device import AirLinkState, ReadError
from .lifecycle import ConnectionPhase


CODEC_OPTIONS = (
    ("ldac", "LDAC"),
    ("aptxAdaptive", "aptX Adaptive"),
    ("aptXHD", "aptX HD"),
    ("aptX", "aptX"),
    ("aptXLL", "aptX Low Latency"),
)
PAIRING_MODES = {0: "Выключен", 1: "Автоматический", 2: "Ручной"}
APTX_MODES = {2: "Низкая задержка", 3: "Высокое качество", 19: "Lossless"}
LDAC_MODES = {
    0: "HQ (990/909 кбит/с)",
    1: "SQ (660/606 кбит/с)",
    2: "MQ (330/303 кбит/с)",
}


def text(value: str, variant: str = "body") -> dict[str, Any]:
    return {"type": "text", "value": value, "variant": variant}


def stack(*children: dict[str, Any], gap: str = "medium") -> dict[str, Any]:
    return {"type": "stack", "gap": gap, "children": list(children)}


def field(label: str, value: str) -> dict[str, Any]:
    return stack(text(label, "label"), text(value, "value"), gap="tiny")


def error_component(error: ReadError | None) -> dict[str, Any] | None:
    if error is None:
        return None
    return text(f"Команда {error.command}: {error.message}", "error")


def compact(*components: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [component for component in components if component is not None]


def card(title: str, *children: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "type": "card",
        "title": title,
        "children": compact(*children),
    }


def build_document(
    *,
    snapshot: ConnectionSnapshot | None,
    status: str,
    status_tone: str,
    phase: ConnectionPhase = ConnectionPhase.OFFLINE,
    auto_connect: bool = True,
    revision: int | str = 0,
    build_info: BuildInfo | None = None,
    view: str = "overview",
    diagnostics: dict[str, Any] | None = None,
    pairing_active: bool = False,
    pairing_target: tuple[int, ...] | None = None,
    discovered_devices: tuple[Any, ...] = (),
    language: str = "en",
) -> dict[str, Any]:
    connected = snapshot is not None
    badge_value, badge_tone = _phase_badge(phase, connected)
    return {
        "schema": "fiiocontrol.bdui/v1",
        "revision": revision,
        "header": {
            "type": "row",
            "align": "center",
            "justify": "between",
            "wrap": True,
            "children": [
                stack(
                    text("FALC", "brand"),
                    text("FIIO AIR LINK CONTROL", "brand-caption"),
                    gap="tiny",
                ),
                {
                    "type": "row",
                    "align": "center",
                    "variant": "navigation",
                    "children": [
                        {
                            "type": "button",
                            "label": "Обзор",
                            "action": "show_overview",
                            "variant": (
                                "navigation-active"
                                if view == "overview"
                                else "navigation"
                            ),
                        },
                        {
                            "type": "button",
                            "label": "Аудио",
                            "action": "show_audio",
                            "variant": (
                                "navigation-active"
                                if view == "audio"
                                else "navigation"
                            ),
                        },
                        {
                            "type": "button",
                            "label": "Устройства",
                            "action": "show_devices",
                            "variant": (
                                "navigation-active"
                                if view == "devices"
                                else "navigation"
                            ),
                        },
                        {
                            "type": "button",
                            "label": "Диагностика",
                            "action": "show_diagnostics",
                            "variant": (
                                "navigation-active"
                                if view == "diagnostics"
                                else "navigation"
                            ),
                        },
                    ],
                },
                {
                    "type": "select",
                    "value": language,
                    "action": "set_language",
                    "ariaLabel": "Language",
                    "options": [
                        {"value": "en", "label": "English"},
                        {"value": "ru", "label": "Русский"},
                    ],
                },
            ],
        },
        "content": _content_for_view(
            view=view,
            snapshot=snapshot,
            phase=phase,
            auto_connect=auto_connect,
            build_info=build_info,
            diagnostics=diagnostics or {},
            pairing_active=pairing_active,
            pairing_target=pairing_target,
            discovered_devices=discovered_devices,
        ),
        "footer": {
            "type": "status",
            "value": status,
            "tone": status_tone,
            "badge": {
                "type": "badge",
                "value": badge_value,
                "tone": badge_tone,
            },
        },
    }


def _content_for_view(
    *,
    view: str,
    snapshot: ConnectionSnapshot | None,
    phase: ConnectionPhase,
    auto_connect: bool,
    build_info: BuildInfo | None,
    diagnostics: dict[str, Any],
    pairing_active: bool,
    pairing_target: tuple[int, ...] | None,
    discovered_devices: tuple[Any, ...],
) -> dict[str, Any]:
    if view == "diagnostics":
        return _diagnostics_content(snapshot, diagnostics, build_info)
    if snapshot is None:
        return _disconnected_content(phase, auto_connect)
    if view == "audio":
        return _audio_content(snapshot)
    if view == "devices":
        return _devices_content(
            snapshot,
            pairing_active,
            pairing_target,
            discovered_devices,
        )
    return _overview_content(snapshot, build_info)


def _disconnected_content(
    phase: ConnectionPhase, auto_connect: bool
) -> dict[str, Any]:
    content = {
        ConnectionPhase.SEARCHING: (
            "Ожидание устройства",
            "Подключите FIIO Air Link по USB. Приложение автоматически обнаружит "
            "управляющую HID-коллекцию и начнёт синхронизацию.",
            "Проверить сейчас",
        ),
        ConnectionPhase.CONNECTING: (
            "Подключение к Air Link",
            "Управляющий HID-интерфейс найден. Выполняется чтение состояния устройства.",
            "Подключение...",
        ),
        ConnectionPhase.RECONNECTING: (
            "Ожидание повторного подключения",
            "USB-соединение потеряно. Подключите Air Link снова, восстановление "
            "выполнится автоматически.",
            "Повторить сейчас",
        ),
        ConnectionPhase.ERROR: (
            "Не удалось подключиться",
            "Проверьте USB-подключение и повторите попытку.",
            "Повторить подключение",
        ),
    }.get(
        phase,
        (
            "Подключение к устройству",
            "Автоматическое подключение приостановлено. Подключите FIIO Air Link "
            "по USB и запустите новую сессию.",
            "Подключить FIIO Air Link",
        ),
    )
    return {
        "type": "hero",
        "eyebrow": "USB / HID CONTROL",
        "title": content[0],
        "description": content[1],
        "action": {
            "type": "button",
            "label": content[2],
            "action": "connect",
            "pendingLabel": "Подключение...",
            "variant": "primary",
            "disabled": phase == ConnectionPhase.CONNECTING,
        },
        "autoConnect": auto_connect,
    }


def _page_header(
    title: str,
    subtitle: str,
    *actions: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "row",
        "align": "end",
        "justify": "between",
        "wrap": True,
        "children": [
            stack(text(title, "title"), text(subtitle, "muted"), gap="tiny"),
            {"type": "row", "align": "center", "children": list(actions)},
        ],
    }


def _overview_content(
    snapshot: ConnectionSnapshot, build_info: BuildInfo | None
) -> dict[str, Any]:
    state = snapshot.state
    connection = state.connection_status
    enabled_codecs = [
        label for key, label in CODEC_OPTIONS if state.codecs.get(key)
    ]
    connected_devices = [
        device.name or "Неизвестное устройство"
        for device in state.paired_devices
        if device.connected
    ]
    connection_value = (
        "Нет подключения"
        if connection is None or not connection.connected
        else ", ".join(connected_devices) or "Подключено"
    )
    brightness = (
        "Нет данных" if state.brightness_raw is None else f"raw {state.brightness_raw}"
    )
    return stack(
        _page_header(
            snapshot.product_name,
            f"Прошивка {state.firmware or 'неизвестна'}",
            {
                "type": "button",
                "label": "Обновить",
                "action": "refresh",
                "pendingLabel": "Чтение...",
                "variant": "secondary",
            },
            {
                "type": "button",
                "label": "Отключить",
                "action": "disconnect",
                "pendingLabel": "Отключение...",
                "variant": "danger",
            },
        ),
        {
            "type": "grid",
            "minimum": 210,
            "children": [
                card(
                    "Подключение",
                    field("Активное устройство", connection_value),
                    field(
                        "Подключено гарнитур",
                        str(connection.connected_headsets) if connection else "0",
                    ),
                    error_component(state.errors["connection_status"]),
                    {
                        "type": "button",
                        "label": "Управление устройствами",
                        "action": "show_devices",
                        "variant": "secondary",
                    },
                ),
                card(
                    "Аудио",
                    field(
                        "Включённые кодеки",
                        ", ".join(enabled_codecs) or "Нет дополнительных кодеков",
                    ),
                    field(
                        "LDAC",
                        _format_mode(LDAC_MODES, state.ldac_mode)
                        if state.codecs.get("ldac")
                        else "Выключен",
                    ),
                    field(
                        "aptX Adaptive",
                        _format_mode(APTX_MODES, state.aptx_mode)
                        if state.codecs.get("aptxAdaptive")
                        else "Выключен",
                    ),
                    {
                        "type": "button",
                        "label": "Настроить аудио",
                        "action": "show_audio",
                        "variant": "secondary",
                    },
                ),
                card(
                    "Устройство",
                    field("Bluetooth-имя", state.local_name or "Нет данных"),
                    error_component(state.errors["local_name"]),
                    field("Яркость индикатора", brightness),
                    error_component(state.errors["brightness_raw"]),
                ),
                _build_card(snapshot, build_info),
            ],
        },
        gap="large",
    )


def _audio_content(snapshot: ConnectionSnapshot) -> dict[str, Any]:
    state = snapshot.state
    aptx = (
        _format_mode(APTX_MODES, state.aptx_mode)
        if state.codecs.get("aptxAdaptive")
        else "Кодек выключен"
    )
    ldac = (
        _format_mode(LDAC_MODES, state.ldac_mode)
        if state.codecs.get("ldac")
        else "Кодек выключен"
    )
    return stack(
        _page_header(
            "Аудио",
            "Разрешённые кодеки и режимы качества",
            {
                "type": "button",
                "label": "Обновить",
                "action": "refresh",
                "pendingLabel": "Чтение...",
                "variant": "secondary",
            },
        ),
        {
            "type": "grid",
            "minimum": 380,
            "children": [
                _codec_form(state, snapshot.capabilities.write_codecs),
                card(
                    "Режимы качества",
                    field("aptX Adaptive", aptx),
                    _mode_control(
                        state.aptx_mode,
                        APTX_MODES,
                        "set_aptx_mode",
                        enabled=(
                            state.codecs.get("aptxAdaptive", False)
                            and snapshot.capabilities.write_aptx_mode
                        ),
                    ),
                    error_component(state.errors["aptx_mode"]),
                    field("LDAC", ldac),
                    _mode_control(
                        state.ldac_mode,
                        LDAC_MODES,
                        "set_ldac_mode",
                        enabled=(
                            state.codecs.get("ldac", False)
                            and snapshot.capabilities.write_ldac_mode
                        ),
                    ),
                    error_component(state.errors["ldac_mode"]),
                ),
            ],
        },
        gap="large",
    )


def _devices_content(
    snapshot: ConnectionSnapshot,
    pairing_active: bool,
    pairing_target: tuple[int, ...] | None,
    discovered_devices: tuple[Any, ...],
) -> dict[str, Any]:
    state = snapshot.state
    connection = state.connection_status
    pairing = (
        "Нет данных"
        if state.pairing_status is None
        else PAIRING_MODES.get(
            state.pairing_status, f"Неизвестно (raw {state.pairing_status})"
        )
    )
    connection_value = (
        "Нет данных"
        if connection is None
        else (
            f"{'Подключено' if connection.connected else 'Нет подключения'}; "
            f"гарнитур: {connection.connected_headsets}; "
            f"LE: {connection.connected_le_devices}"
        )
    )
    return stack(
        _page_header(
            "Устройства",
            "Подключение и управление Bluetooth-приёмниками",
            {
                "type": "button",
                "label": "Обновить",
                "action": "refresh",
                "pendingLabel": "Чтение...",
                "variant": "secondary",
            },
        ),
        card(
            "Добавление устройства",
            field("Режим сопряжения", pairing),
            error_component(state.errors["pairing_status"]),
            field("Текущее соединение", connection_value),
            error_component(state.errors["connection_status"]),
            {
                "type": "button",
                "label": (
                    "Остановить поиск"
                    if pairing_active
                    else "Добавить новое устройство"
                ),
                "action": "stop_pairing" if pairing_active else "start_pairing",
                "pendingLabel": "Остановка..." if pairing_active else "Запуск...",
                "variant": "danger" if pairing_active else "primary",
                "disabled": not snapshot.capabilities.pairing,
            },
            (
                text(
                    "Отключите устройство от других источников и включите "
                    "режим сопряжения.",
                    "note",
                )
                if pairing_active
                else None
            ),
        ),
        *(
            [_discovered_devices(discovered_devices, pairing_target)]
            if pairing_active
            else []
        ),
        _paired_devices(state, snapshot.capabilities.manage_connections),
        gap="large",
    )


def _codec_form(state: AirLinkState, can_write: bool) -> dict[str, Any]:
    read_failed = state.errors["codecs"] is not None
    disabled = read_failed or not can_write
    return {
        "type": "card",
        "title": "Bluetooth-кодеки",
        "children": [
            {
                "type": "form",
                "id": "codecs",
                "initial": state.codecs,
                "children": [
                    {
                        "type": "checkbox",
                        "name": name,
                        "label": label,
                        "disabled": disabled,
                    }
                    for name, label in CODEC_OPTIONS
                ],
                "submit": {
                    "type": "button",
                    "label": "Применить кодеки",
                    "action": "set_codecs",
                    "pendingLabel": "Запись...",
                    "variant": "primary",
                    "disabled": disabled,
                },
            },
            *compact(error_component(state.errors["codecs"])),
            *(
                []
                if can_write
                else [
                    text(
                        "Запись кодеков отключена: firmware не прошла аппаратную проверку.",
                        "error",
                    )
                ]
            ),
            text(
                "Фактический кодек зависит также от приёмника и условий радиосвязи.",
                "note",
            ),
        ],
    }


def _mode_control(
    value: int | None,
    modes: dict[int, str],
    action: str,
    *,
    enabled: bool,
) -> dict[str, Any]:
    return {
        "type": "segmented",
        "value": value,
        "action": action,
        "disabled": not enabled,
        "options": [
            {"value": mode, "label": label} for mode, label in modes.items()
        ],
    }


def _paired_devices(
    state: AirLinkState, can_manage_connections: bool
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if not state.paired_devices:
        rows.append(text("Устройства не найдены.", "muted"))
    for device in state.paired_devices:
        address = ":".join(f"{byte:02x}" for byte in device.address)
        rows.append(
            {
                "type": "row",
                "align": "center",
                "justify": "between",
                "wrap": True,
                "variant": "device",
                "children": [
                    stack(
                        text(device.name or "Неизвестное устройство", "value"),
                        text(address, "mono"),
                        *compact(error_component(device.name_error)),
                        gap="tiny",
                    ),
                    {
                        "type": "row",
                        "align": "center",
                        "wrap": True,
                        "children": [
                            {
                                "type": "badge",
                                "value": (
                                    "ПОДКЛЮЧЕНО"
                                    if device.connected
                                    else "НЕ ПОДКЛЮЧЕНО"
                                ),
                                "tone": "success" if device.connected else "muted",
                            },
                            {
                                "type": "button",
                                "label": (
                                    "Отключить" if device.connected else "Подключить"
                                ),
                                "action": (
                                    "disconnect_paired_device"
                                    if device.connected
                                    else "connect_paired_device"
                                ),
                                "payload": {"address": list(device.address)},
                                "pendingLabel": (
                                    "Отключение..."
                                    if device.connected
                                    else "Подключение..."
                                ),
                                "variant": (
                                    "danger" if device.connected else "primary"
                                ),
                                "disabled": not can_manage_connections,
                            },
                        ],
                    },
                ],
            }
        )
    return card(
        "Сопряжённые устройства",
        error_component(state.errors["paired_devices"]),
        *rows,
    )


def _discovered_devices(
    devices: tuple[Any, ...], pairing_target: tuple[int, ...] | None
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if not devices:
        rows.append(text("Поиск Bluetooth-устройств...", "muted"))
    for device in devices:
        address = ":".join(f"{byte:02x}" for byte in device.address)
        selected = pairing_target == device.address
        rows.append(
            {
                "type": "row",
                "align": "center",
                "justify": "between",
                "wrap": True,
                "variant": "device",
                "children": [
                    stack(
                        text(device.name or "Неизвестное устройство", "value"),
                        text(address, "mono"),
                        gap="tiny",
                    ),
                    {
                        "type": "button",
                        "label": "Ожидание..." if selected else "Сопрячь",
                        "action": "pair_discovered_device",
                        "payload": {"address": list(device.address)},
                        "pendingLabel": "Сопряжение...",
                        "variant": "primary",
                        "disabled": pairing_target is not None,
                    },
                ],
            }
        )
    return card("Найденные устройства", *rows)


def _build_card(
    snapshot: ConnectionSnapshot, build_info: BuildInfo | None
) -> dict[str, Any]:
    build = build_info or BuildInfo("unknown", None, False)
    return card(
        "Система",
        field("Версия приложения", build.version),
        field("Сборка", build.display_commit),
        {
            "type": "button",
            "label": "Открыть диагностику",
            "action": "show_diagnostics",
            "variant": "secondary",
        },
    )


def _diagnostics_content(
    snapshot: ConnectionSnapshot | None,
    diagnostics: dict[str, Any],
    build_info: BuildInfo | None,
) -> dict[str, Any]:
    counters = diagnostics.get("counters", {})
    descriptor = snapshot.descriptor if snapshot else None
    state = snapshot.state if snapshot else None
    build = build_info or BuildInfo("unknown", None, False)
    path = descriptor.path.decode(errors="replace") if descriptor else "Нет данных"
    summary = {
        "type": "grid",
        "minimum": 300,
        "children": [
            card(
                "Устройство",
                field("VID / PID", "0x2972 / 0x0158"),
                field("Firmware", state.firmware if state else "Нет подключения"),
                field("HID reports", "OUT 7 × 446; IN 8 × 446; EVENT 9 × 11"),
                field(
                    "Interface / usage",
                    (
                        f"{descriptor.interface_number} / "
                        f"{descriptor.usage_page:#06x}:{descriptor.usage}"
                        if descriptor and descriptor.usage_page is not None
                        else "Нет данных"
                    ),
                ),
                {"type": "copy", "label": "HID path", "value": path},
            ),
            card(
                "Обмен",
                field("Успешных запросов", str(counters.get("responses", 0))),
                field("Timeout", str(counters.get("timeouts", 0))),
                field("Ошибок HID I/O", str(counters.get("io_errors", 0))),
                field("Malformed packets", str(counters.get("malformed", 0))),
                field(
                    "Последний успешный ответ",
                    diagnostics.get("last_success_at") or "Нет данных",
                ),
            ),
            card(
                "Lifecycle",
                field("Disconnect", str(counters.get("disconnects", 0))),
                field(
                    "Попыток reconnect",
                    str(counters.get("reconnect_attempts", 0)),
                ),
                field(
                    "Успешных reconnect",
                    str(counters.get("reconnect_successes", 0)),
                ),
                field("Notifications", str(counters.get("notifications", 0))),
            ),
            card(
                "Сборка",
                field("Версия", build.version),
                field("Commit", build.display_commit),
                field(
                    "Packet logger",
                    "Включён" if diagnostics.get("debug") else "Выключен",
                ),
                text(
                    "Для raw packet log запустите приложение с "
                    "FIIO_AIR_LINK_DEBUG=1. Экспорт всегда скрывает payload.",
                    "note",
                ),
            ),
        ],
    }
    records = diagnostics.get("records", [])
    packet_content: dict[str, Any]
    if records:
        packet_content = {
            "type": "table",
            "columns": [
                {"key": "timestamp", "label": "Время"},
                {"key": "category", "label": "Тип"},
                {"key": "report_id", "label": "Report"},
                {"key": "feature_byte", "label": "Feature"},
                {"key": "command", "label": "Command"},
                {"key": "payload_length", "label": "Payload"},
                {"key": "packet", "label": "Пакет"},
            ],
            "rows": list(reversed(records)),
            "empty": "Пакеты не записаны.",
        }
    else:
        packet_content = stack(
            text("Журнал пакетов пуст.", "muted"),
            text(
                "Raw packets сохраняются только в development-режиме. Счётчики "
                "и время успешного ответа работают всегда.",
                "note",
            ),
        )
    return stack(
        {
            "type": "row",
            "align": "end",
            "justify": "between",
            "wrap": True,
            "children": [
                stack(
                    text("Диагностика", "title"),
                    text("HID transport и состояние приложения", "muted"),
                    gap="tiny",
                ),
                {
                    "type": "button",
                    "label": "Экспортировать JSON",
                    "action": "export_diagnostics",
                    "pendingLabel": "Сохранение...",
                    "variant": "secondary",
                },
            ],
        },
        {
            "type": "tabs",
            "tabs": [
                {"label": "Сводка", "content": summary},
                {"label": "Пакеты", "content": packet_content},
            ],
        },
        gap="large",
    )


def _phase_badge(
    phase: ConnectionPhase, connected: bool
) -> tuple[str, str]:
    if phase == ConnectionPhase.SYNCHRONIZING:
        return "SYNCING", "warning"
    if connected:
        return "CONNECTED", "success"
    return {
        ConnectionPhase.SEARCHING: ("SEARCHING", "muted"),
        ConnectionPhase.CONNECTING: ("CONNECTING", "warning"),
        ConnectionPhase.RECONNECTING: ("RECONNECTING", "warning"),
        ConnectionPhase.ERROR: ("ERROR", "error"),
    }.get(phase, ("OFFLINE", "error"))


def _format_mode(modes: dict[int, str], value: int | None) -> str:
    if value is None:
        return "Нет данных"
    return modes.get(value, f"Неизвестно (raw {value})")
