from __future__ import annotations

import json
import os
import threading
from pathlib import Path


SETTINGS_VERSION = 1
SUPPORTED_LANGUAGES = frozenset(("en", "ru"))


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_path()
        self._lock = threading.RLock()
        self._language = "en"
        self._load()

    @property
    def language(self) -> str:
        with self._lock:
            return self._language

    def set_language(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        with self._lock:
            if self._language == language and self.path.exists():
                return
            self._language = language
            self._write()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            language = document.get("language")
            if document.get("version") == SETTINGS_VERSION and language in SUPPORTED_LANGUAGES:
                self._language = language
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._language = "en"

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(
                {"version": SETTINGS_VERSION, "language": self._language},
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _default_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "FIIO Air Link Control" / "settings.json"
