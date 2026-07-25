from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import __version__


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str
    commit: str | None
    dirty: bool

    @property
    def display_commit(self) -> str:
        if not self.commit:
            return "unknown"
        return f"{self.commit[:8]}{'-dirty' if self.dirty else ''}"


def get_build_info() -> BuildInfo:
    embedded = _read_embedded_info()
    if embedded is not None:
        return embedded

    commit = os.environ.get("FIIO_BUILD_COMMIT")
    dirty = os.environ.get("FIIO_BUILD_DIRTY") == "1"
    if commit:
        return BuildInfo(__version__, commit, dirty)

    return _read_git_info()


def _read_embedded_info() -> BuildInfo | None:
    path = Path(__file__).with_name("build_info.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return BuildInfo(
        version=str(data.get("version") or __version__),
        commit=str(data["commit"]) if data.get("commit") else None,
        dirty=bool(data.get("dirty", False)),
    )


def _read_git_info() -> BuildInfo:
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return BuildInfo(__version__, commit or None, bool(status.strip()))
    except (OSError, subprocess.CalledProcessError):
        return BuildInfo(__version__, None, False)
