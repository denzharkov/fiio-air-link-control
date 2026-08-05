from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
NAME = "FIIO-Air-Link-Control"


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows executable must be built on Windows")
    try:
        from PyInstaller.__main__ import run
    except ImportError as error:
        raise SystemExit(
            "PyInstaller is not installed. Run: python -m pip install -e .[build]"
        ) from error

    build_dir = ROOT / "build" / "pyinstaller"
    spec_dir = ROOT / "build"
    generated_dir = ROOT / "build" / "generated"
    RELEASE.mkdir(exist_ok=True)
    for path in (
        build_dir,
        spec_dir / f"{NAME}.spec",
        RELEASE / f"{NAME}.exe",
    ):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    generated_dir.mkdir(parents=True, exist_ok=True)
    build_info = generated_dir / "build_info.json"
    build_info.write_text(
        json.dumps(
            {
                "version": _project_version(),
                "commit": _git_output("rev-parse", "HEAD"),
                "dirty": bool(_git_output("status", "--porcelain")),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    run(
        [
            str(ROOT / "scripts" / "pyinstaller_entry.py"),
            "--name",
            NAME,
            "--onefile",
            "--windowed",
            "--icon",
            str(ROOT / "assets" / "app-icon.ico"),
            "--clean",
            "--noconfirm",
            "--paths",
            str(ROOT),
            "--distpath",
            str(RELEASE),
            "--workpath",
            str(build_dir),
            "--specpath",
            str(spec_dir),
            "--hidden-import",
            "hid",
            "--add-data",
            f"{ROOT / 'fiiocontrol' / 'web'};fiiocontrol/web",
            "--add-data",
            f"{build_info};fiiocontrol",
        ]
    )


def _project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as source:
        return str(tomllib.load(source)["project"]["version"])


def _git_output(*arguments: str) -> str | None:
    try:
        value = subprocess.check_output(
            ["git", *arguments],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return value or None
    except (OSError, subprocess.CalledProcessError):
        return None


if __name__ == "__main__":
    main()
