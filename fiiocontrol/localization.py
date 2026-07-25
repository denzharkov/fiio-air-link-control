from __future__ import annotations

import re
from typing import Any


RU_TO_EN = {
    "Обзор": "Overview",
    "Аудио": "Audio",
    "Устройства": "Devices",
    "Диагностика": "Diagnostics",
    "Выключен": "Off",
    "Автоматический": "Automatic",
    "Ручной": "Manual",
    "Низкая задержка": "Low latency",
    "Высокое качество": "High quality",
    "HQ (990/909 кбит/с)": "HQ (990/909 kbps)",
    "SQ (660/606 кбит/с)": "SQ (660/606 kbps)",
    "MQ (330/303 кбит/с)": "MQ (330/303 kbps)",
    "Ожидание устройства": "Waiting for device",
    "Подключите FIIO Air Link по USB. Приложение автоматически обнаружит управляющую HID-коллекцию и начнёт синхронизацию.": "Connect FIIO Air Link via USB. The application will detect the control HID interface and synchronize automatically.",
    "Проверить сейчас": "Check now",
    "Подключение к Air Link": "Connecting to Air Link",
    "Управляющий HID-интерфейс найден. Выполняется чтение состояния устройства.": "The control HID interface was found. Reading device state.",
    "Подключение...": "Connecting...",
    "Ожидание повторного подключения": "Waiting to reconnect",
    "USB-соединение потеряно. Подключите Air Link снова, восстановление выполнится автоматически.": "USB connection was lost. Reconnect Air Link to restore the session automatically.",
    "Повторить сейчас": "Retry now",
    "Не удалось подключиться": "Connection failed",
    "Проверьте USB-подключение и повторите попытку.": "Check the USB connection and try again.",
    "Повторить подключение": "Retry connection",
    "Подключение к устройству": "Device connection",
    "Автоматическое подключение приостановлено. Подключите FIIO Air Link по USB и запустите новую сессию.": "Automatic connection is paused. Connect FIIO Air Link via USB and start a new session.",
    "Подключить FIIO Air Link": "Connect FIIO Air Link",
    "Неизвестное устройство": "Unknown device",
    "Нет подключения": "Not connected",
    "Подключено": "Connected",
    "Нет данных": "No data",
    "неизвестна": "unknown",
    "Обновить": "Refresh",
    "Чтение...": "Reading...",
    "Отключить": "Disconnect",
    "Отключение...": "Disconnecting...",
    "Подключение": "Connection",
    "Активное устройство": "Active device",
    "Подключено гарнитур": "Connected headsets",
    "Управление устройствами": "Manage devices",
    "Включённые кодеки": "Enabled codecs",
    "Нет дополнительных кодеков": "No optional codecs",
    "Настроить аудио": "Configure audio",
    "Устройство": "Device",
    "Bluetooth-имя": "Bluetooth name",
    "Яркость индикатора": "Indicator brightness",
    "Разрешённые кодеки и режимы качества": "Enabled codecs and quality modes",
    "Кодек выключен": "Codec is disabled",
    "Режимы качества": "Quality modes",
    "Подключение и управление Bluetooth-приёмниками": "Connect and manage Bluetooth receivers",
    "Добавление устройства": "Add device",
    "Режим сопряжения": "Pairing mode",
    "Текущее соединение": "Current connection",
    "Остановить поиск": "Stop search",
    "Добавить новое устройство": "Add new device",
    "Остановка...": "Stopping...",
    "Запуск...": "Starting...",
    "Отключите устройство от других источников и включите режим сопряжения.": "Disconnect the device from other sources and enable pairing mode.",
    "Bluetooth-кодеки": "Bluetooth codecs",
    "Применить кодеки": "Apply codecs",
    "Запись...": "Writing...",
    "Запись кодеков отключена: firmware не прошла аппаратную проверку.": "Codec changes are disabled because this firmware has not been hardware-verified.",
    "Фактический кодек зависит также от приёмника и условий радиосвязи.": "The negotiated codec also depends on the receiver and radio conditions.",
    "Устройства не найдены.": "No devices found.",
    "ПОДКЛЮЧЕНО": "CONNECTED",
    "НЕ ПОДКЛЮЧЕНО": "NOT CONNECTED",
    "Подключить": "Connect",
    "Сопряжённые устройства": "Paired devices",
    "Поиск Bluetooth-устройств...": "Searching for Bluetooth devices...",
    "Ожидание...": "Waiting...",
    "Сопрячь": "Pair",
    "Сопряжение...": "Pairing...",
    "Найденные устройства": "Discovered devices",
    "Система": "System",
    "Версия приложения": "Application version",
    "Сборка": "Build",
    "Открыть диагностику": "Open diagnostics",
    "Обмен": "Transport",
    "Успешных запросов": "Successful requests",
    "Ошибок HID I/O": "HID I/O errors",
    "Последний успешный ответ": "Last successful response",
    "Попыток reconnect": "Reconnect attempts",
    "Успешных reconnect": "Successful reconnects",
    "Версия": "Version",
    "Включён": "Enabled",
    "Для raw packet log запустите приложение с FIIO_AIR_LINK_DEBUG=1. Экспорт всегда скрывает payload.": "Start the application with FIIO_AIR_LINK_DEBUG=1 to capture raw packets. Exported payloads are always redacted.",
    "Время": "Time",
    "Тип": "Type",
    "Пакет": "Packet",
    "Пакеты не записаны.": "No packets recorded.",
    "Журнал пакетов пуст.": "Packet log is empty.",
    "Raw packets сохраняются только в development-режиме. Счётчики и время успешного ответа работают всегда.": "Raw packets are stored only in development mode. Counters and the last successful response are always available.",
    "HID transport и состояние приложения": "HID transport and application state",
    "Экспортировать JSON": "Export JSON",
    "Сохранение...": "Saving...",
    "Сводка": "Summary",
    "Пакеты": "Packets",
    "Ожидание FIIO Air Link...": "Waiting for FIIO Air Link...",
    "Отключено пользователем": "Disconnected by user",
    "Air Link: чтение состояния...": "Air Link: reading state...",
    "Air Link: запись кодеков...": "Air Link: writing codecs...",
    "Air Link: запуск сопряжения...": "Air Link: starting pairing...",
    "Сопряжение запущено. Включите pairing на новом устройстве.": "Pairing started. Enable pairing mode on the new device.",
    "Сопряжение остановлено": "Pairing stopped",
    "Сначала запустите сопряжение": "Start pairing first",
    "Обнаруженное устройство больше недоступно": "The discovered device is no longer available",
    "Устройство больше не доступно. Запустите pairing повторно.": "The device is no longer available. Start pairing again.",
    "Время сопряжения истекло": "Pairing timed out",
    "Сопряжение не выполнено. Снова включите pairing на наушниках.": "Pairing failed. Enable pairing mode on the headphones again.",
    "Новое устройство сопряжено": "New device paired",
    "Air Link: повторное подключение...": "Air Link: reconnecting...",
    "Air Link: подключение...": "Air Link: connecting...",
    "Air Link отключён. Ожидание повторного подключения...": "Air Link disconnected. Waiting to reconnect...",
    "Air Link подключён, часть чтений завершилась ошибкой": "Air Link connected, but some values could not be read",
    "Air Link не подключён": "Air Link is not connected",
    "FIIO Air Link не найден. Подключите устройство по USB.": "FIIO Air Link was not found. Connect it via USB.",
    "Запись кодеков не подтверждена для этой firmware": "Codec changes are not verified for this firmware",
    "Запись режима aptX Adaptive не подтверждена для этой firmware": "aptX Adaptive mode changes are not verified for this firmware",
    "Сначала включите aptX Adaptive": "Enable aptX Adaptive first",
    "Запись режима LDAC не подтверждена для этой firmware": "LDAC mode changes are not verified for this firmware",
    "Сначала включите LDAC": "Enable LDAC first",
    "Режим сопряжения не подтверждён для этой firmware": "Pairing mode is not verified for this firmware",
    "Сопряжение не подтверждено для этой firmware": "Pairing is not verified for this firmware",
    "Сопряжение не поддерживается": "Pairing is not supported",
    "Управление подключениями не подтверждено для этой firmware": "Connection management is not verified for this firmware",
    "Сопряжённое устройство не найдено": "Paired device was not found",
    "Некорректное значение режима качества": "Invalid quality mode value",
    "Некорректный набор кодеков": "Invalid codec set",
    "Некорректный Bluetooth-адрес": "Invalid Bluetooth address",
}


def localize_document(document: dict[str, Any], language: str) -> dict[str, Any]:
    if language == "ru":
        return document
    return _walk(document)


def _walk(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _walk(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item) for item in value)
    if isinstance(value, str):
        return translate_text(value)
    return value


def translate_text(value: str) -> str:
    exact = RU_TO_EN.get(value)
    if exact is not None:
        return exact
    if value.startswith("Прошивка "):
        return f"Firmware {value.removeprefix('Прошивка ')}"
    if value.startswith("Команда "):
        return value.replace("Команда ", "Command ", 1)
    if value.startswith("Неизвестно (raw "):
        return value.replace("Неизвестно", "Unknown", 1)
    if value.startswith("Ошибка: "):
        return f"Error: {translate_text(value.removeprefix('Ошибка: '))}"
    if value.startswith("Ошибка обнаружения HID: "):
        return f"HID detection error: {value.removeprefix('Ошибка обнаружения HID: ')}"
    if value.startswith("Соединение потеряно: "):
        return f"Connection lost: {value.removeprefix('Соединение потеряно: ')}"
    if value.startswith("Ожидание Air Link: "):
        return f"Waiting for Air Link: {value.removeprefix('Ожидание Air Link: ')}"
    if value.startswith("Диагностика сохранена: "):
        return f"Diagnostics saved: {value.removeprefix('Диагностика сохранена: ')}"
    if value.startswith("Сопряжение с "):
        return f"Pairing with {value.removeprefix('Сопряжение с ')}"
    if value.endswith(" сопряжено"):
        return f"{value.removesuffix(' сопряжено')} paired"
    match = re.fullmatch(r"(Подключено|Нет подключения); гарнитур: (\d+); LE: (\d+)", value)
    if match:
        state = "Connected" if match.group(1) == "Подключено" else "Not connected"
        return f"{state}; headsets: {match.group(2)}; LE: {match.group(3)}"
    if value.startswith("Air Link: запись режима "):
        return f"Air Link: writing {value.removeprefix('Air Link: запись режима ')}"
    if value == "Air Link: подключение устройства...":
        return "Air Link: connecting device..."
    if value == "Air Link: отключение устройства...":
        return "Air Link: disconnecting device..."
    return value
