from __future__ import annotations

import argparse
import html
import json
import os
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
        raise SystemExit("MSIX packages must be built on Windows")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--identity-name",
        default=os.environ.get("STORE_IDENTITY_NAME", "FIIOAirLinkControl.Dev"),
    )
    parser.add_argument(
        "--publisher",
        default=os.environ.get(
            "STORE_PUBLISHER", "CN=FIIO Air Link Control Development"
        ),
    )
    parser.add_argument(
        "--publisher-display-name",
        default=os.environ.get(
            "STORE_PUBLISHER_DISPLAY_NAME", "FIIO Air Link Control contributors"
        ),
    )
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--store", action="store_true")
    options = parser.parse_args()

    if options.identity_file:
        identity = json.loads(options.identity_file.read_text(encoding="utf-8"))
        options.identity_name = identity["identity_name"]
        options.publisher = identity["publisher"]
        options.publisher_display_name = identity["publisher_display_name"]

    if options.store and (
        options.identity_name.endswith(".Dev")
        or options.publisher.endswith("Development")
    ):
        raise SystemExit("Store identity values from Partner Center are required")

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_windows.py"), "--onedir"],
        cwd=ROOT,
        check=True,
    )

    package_dir = ROOT / "build" / "msix" / "package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.copytree(RELEASE / NAME, package_dir)
    _prune_x64_payload(package_dir)
    shutil.copytree(ROOT / "assets" / "store", package_dir / "Assets")

    version = _msix_version()
    manifest = (ROOT / "packaging" / "AppxManifest.xml.in").read_text(
        encoding="utf-8"
    )
    replacements = {
        "@IDENTITY_NAME@": options.identity_name,
        "@PUBLISHER@": options.publisher,
        "@PUBLISHER_DISPLAY_NAME@": options.publisher_display_name,
        "@VERSION@": version,
    }
    for placeholder, value in replacements.items():
        manifest = manifest.replace(placeholder, html.escape(value, quote=True))
    (package_dir / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    output = RELEASE / f"{NAME}_{version}_x64.msix"
    output.unlink(missing_ok=True)
    subprocess.run(
        [
            str(_find_makeappx()),
            "pack",
            "/v",
            "/o",
            "/h",
            "SHA256",
            "/d",
            str(package_dir),
            "/p",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    print(output)


def _msix_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as source:
        raw = str(tomllib.load(source)["project"]["version"])
    parts = raw.split("-", 1)[0].split(".")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        raise SystemExit(f"Project version cannot be converted to MSIX: {raw}")
    values = [int(part) for part in parts]
    if any(value > 65535 for value in values):
        raise SystemExit(f"Invalid MSIX version: {raw}")
    if values[0] == 0:
        values[0] = 1
    return ".".join(str(value) for value in [*values, *([0] * (4 - len(values)))])


def _find_makeappx() -> Path:
    roots = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Windows Kits" / "10",
        Path(os.environ.get("ProgramFiles", "")) / "Windows Kits" / "10",
    ]
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(root.glob("bin/*/x64/makeappx.exe"))
        candidates.append(root / "App Certification Kit" / "makeappx.exe")
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        raise SystemExit("MakeAppx.exe was not found; install the Windows SDK")
    return sorted(existing, key=lambda path: str(path), reverse=True)[0]


def _prune_x64_payload(package_dir: Path) -> None:
    relative_paths = (
        "_internal/clr_loader/ffi/dlls/x86",
        "_internal/webview/lib/WebBrowserInterop.x86.dll",
        "_internal/webview/lib/pywebview-android.jar",
        "_internal/webview/lib/runtimes/win-arm64",
        "_internal/webview/lib/runtimes/win-x86",
    )
    for relative_path in relative_paths:
        path = package_dir / relative_path
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
