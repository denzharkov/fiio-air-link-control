from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import webview

from .build_info import BuildInfo, get_build_info
from .device import CODECS
from .lifecycle import AirLinkLifecycle
from .localization import localize_document
from .settings import SettingsStore
from .ui_document import build_document


class BduiBackend:
    """Action dispatcher and document source for the generic UI renderer."""

    def __init__(
        self,
        lifecycle: AirLinkLifecycle | None = None,
        build_info: BuildInfo | None = None,
        settings: SettingsStore | None = None,
    ) -> None:
        self._lifecycle = lifecycle or AirLinkLifecycle()
        self._build_info = build_info or get_build_info()
        self._settings = settings or SettingsStore()
        self._view_lock = threading.Lock()
        self._view = "overview"
        self._view_revision = 0

    def start(self) -> None:
        self._lifecycle.start()

    def get_ui(self) -> dict[str, Any]:
        return self._document()

    def get_revision(self) -> str:
        with self._view_lock:
            return f"{self._lifecycle.revision}.{self._view_revision}"

    def get_language(self) -> str:
        return self._settings.language

    def dispatch(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        supported_actions = {
            "connect",
            "disconnect",
            "refresh",
            "set_codecs",
            "set_aptx_mode",
            "set_ldac_mode",
            "connect_paired_device",
            "disconnect_paired_device",
            "start_pairing",
            "stop_pairing",
            "pair_discovered_device",
            "show_overview",
            "show_audio",
            "show_devices",
            "show_diagnostics",
            "export_diagnostics",
            "set_language",
        }
        if action not in supported_actions:
            raise ValueError(f"Unknown UI action: {action}")
        try:
            if action == "connect":
                self._lifecycle.connect()
            elif action == "disconnect":
                self._lifecycle.disconnect()
            elif action == "refresh":
                self._lifecycle.refresh()
            elif action == "set_codecs":
                self._lifecycle.set_codecs(self._validate_codecs(payload))
            elif action == "set_aptx_mode":
                self._lifecycle.set_aptx_mode(self._validate_mode(payload))
            elif action == "set_ldac_mode":
                self._lifecycle.set_ldac_mode(self._validate_mode(payload))
            elif action == "connect_paired_device":
                self._lifecycle.connect_paired_device(self._validate_address(payload))
            elif action == "disconnect_paired_device":
                self._lifecycle.disconnect_paired_device(
                    self._validate_address(payload)
                )
            elif action == "start_pairing":
                self._lifecycle.start_pairing()
            elif action == "stop_pairing":
                self._lifecycle.stop_pairing()
            elif action == "pair_discovered_device":
                self._lifecycle.pair_discovered_device(
                    self._validate_address(payload)
                )
            elif action == "show_overview":
                self._set_view("overview")
            elif action == "show_audio":
                self._set_view("audio")
            elif action == "show_devices":
                self._set_view("devices")
            elif action == "show_diagnostics":
                self._set_view("diagnostics")
            elif action == "export_diagnostics":
                path = self._export_diagnostics()
                self._lifecycle.set_status(
                    f"Диагностика сохранена: {path}", "success"
                )
            elif action == "set_language":
                self._set_language(payload)
        except (OSError, ValueError) as error:
            self._lifecycle.set_status(f"Ошибка: {error}", "error")
        return self._document()

    def close(self) -> None:
        self._lifecycle.stop()

    def _document(self) -> dict[str, Any]:
        lifecycle = self._lifecycle.snapshot()
        with self._view_lock:
            view = self._view
        language = self._settings.language
        document = build_document(
            snapshot=lifecycle.connection,
            phase=lifecycle.phase,
            auto_connect=lifecycle.auto_connect,
            status=lifecycle.status,
            status_tone=lifecycle.status_tone,
            revision=self.get_revision(),
            build_info=self._build_info,
            view=view,
            diagnostics=self._lifecycle.diagnostics.snapshot(),
            pairing_active=lifecycle.pairing_active,
            pairing_target=lifecycle.pairing_target,
            discovered_devices=lifecycle.discovered_devices,
            language=language,
        )
        document["locale"] = language
        return localize_document(document, language)

    def _set_view(self, view: str) -> None:
        with self._view_lock:
            if self._view == view:
                return
            self._view = view
            self._view_revision += 1

    def _set_language(self, payload: dict[str, Any] | None) -> None:
        language = str((payload or {}).get("value", ""))
        self._settings.set_language(language)
        with self._view_lock:
            self._view_revision += 1

    def _export_diagnostics(self) -> Path:
        generated_at = datetime.now().astimezone()
        lifecycle = self._lifecycle.snapshot()
        connection = lifecycle.connection
        descriptor = connection.descriptor if connection else None
        state = connection.state if connection else None
        document = {
            "schema": "fiiocontrol.diagnostics/v1",
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "build": {
                "version": self._build_info.version,
                "commit": self._build_info.commit,
                "dirty": self._build_info.dirty,
            },
            "lifecycle": {
                "phase": lifecycle.phase,
                "status": lifecycle.status,
                "auto_connect": lifecycle.auto_connect,
                "revision": lifecycle.revision,
            },
            "device": {
                "vendor_id": "0x2972",
                "product_id": "0x0158",
                "firmware": state.firmware if state else None,
                "paired_device_count": len(state.paired_devices) if state else 0,
                "interface_number": descriptor.interface_number if descriptor else None,
                "usage_page": descriptor.usage_page if descriptor else None,
                "usage": descriptor.usage if descriptor else None,
                "errors": {
                    name: (
                        {
                            "code": error.code,
                            "command": error.command,
                            "message": error.message,
                        }
                        if error
                        else None
                    )
                    for name, error in (state.errors.items() if state else [])
                },
            },
            "transport": self._lifecycle.diagnostics.export_snapshot(),
        }
        destination = Path.home() / "Downloads"
        if not destination.is_dir():
            destination = Path.home()
        filename = f"fiio-air-link-diagnostics-{generated_at:%Y%m%d-%H%M%S}.json"
        path = destination / filename
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _validate_codecs(payload: dict[str, Any] | None) -> dict[str, bool]:
        if not isinstance(payload, dict) or set(payload) != set(CODECS):
            raise ValueError("Некорректный набор кодеков")
        if any(not isinstance(payload[name], bool) for name in CODECS):
            raise ValueError("Некорректный набор кодеков")
        return {name: payload[name] for name in CODECS}

    @staticmethod
    def _validate_mode(payload: dict[str, Any] | None) -> int:
        value = (payload or {}).get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Некорректное значение режима качества")
        return value

    @staticmethod
    def _validate_address(payload: dict[str, Any] | None) -> tuple[int, ...]:
        value = (payload or {}).get("address")
        if not isinstance(value, list) or len(value) != 6:
            raise ValueError("Некорректный Bluetooth-адрес")
        if any(
            isinstance(byte, bool) or not isinstance(byte, int) or not 0 <= byte <= 255
            for byte in value
        ):
            raise ValueError("Некорректный Bluetooth-адрес")
        return tuple(value)


def main() -> None:
    logging.basicConfig(
        level=(
            logging.DEBUG
            if os.environ.get("FIIO_AIR_LINK_DEBUG") == "1"
            else logging.INFO
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    backend = BduiBackend()
    backend.start()
    index = Path(__file__).with_name("web") / "index.html"
    window = webview.create_window(
        "FIIO Air Link Control",
        index.as_uri(),
        js_api=backend,
        width=1100,
        height=820,
        min_size=(760, 600),
        background_color="#0b1013",
    )
    window.events.closed += backend.close
    webview.start(
        gui="edgechromium",
        debug=os.environ.get("FIIO_AIR_LINK_DEBUG") == "1",
        private_mode=True,
    )
