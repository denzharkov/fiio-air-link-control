# Session handoff

## Repository

- GitHub: `https://github.com/denzharkov/fiio-air-link-control`
- Local clone: `C:\Users\denis\Projects\fiio-air-link-control`
- Product name: FIIO Air Link Control (FALC)
- Platform: Windows
- Language: Python 3.11+
- UI: Backend-Driven UI rendered through `pywebview` and WebView2
- HID backend: `hidapi==0.14.0.post4`

## Project layout

```text
fiiocontrol/    Python package and BDUI renderer
tests/          Unit tests
scripts/        Windows build and hardware smoke tests
docs/           Protocol notes and roadmap
pyproject.toml  Packaging and dependencies
```

There is intentionally no `src/` wrapper and no Node.js, Electron, Vite, pnpm,
or WebHID dependency. BDUI assets are in `fiiocontrol/web/`.

## Implemented functionality

- Automatic USB detection, connect, disconnect, and reconnect.
- Serialized Air Link HID commands with one background input reader.
- Strict response matching by feature and command.
- Firmware, local name, codecs, quality modes, pairing state, connection state,
  brightness raw value, and paired-device list reads.
- Direct codec enable/disable with readback.
- LDAC and aptX Adaptive mode writes with readback.
- Connect and disconnect actions for already paired devices.
- Discovery handshake and discovery event parser.
- Diagnostics screen, bounded packet log, counters, and privacy-safe JSON export.
- English default localization and persistent Russian selection.
- FALC startup splash and four pages: Overview, Audio, Devices, Diagnostics.

## Confirmed hardware

- Product VID/PID: `0x2972 / 0x0158`
- Firmware: `1.4.0`
- Output report: ID `7`, 446-byte payload
- Input report: ID `8`, 446-byte payload
- Event report: ID `9`, 11-byte payload
- Control HID usage: page `0xFF00`, usage `3`, interface `1`

Confirmed writes:

- Codec set command `7` followed by GET `6`.
- aptX mode SET `65` followed by GET `64`.
- LDAC mode SET `67` followed by GET `66`.
- Connect command `16` and disconnect command `17` with list/status readback.
- Pairing mode restart `0 -> 2` and stable stop `2 -> 1`.

Discovery handshake:

1. Core command `8`, payload `24`.
2. Read pairing state and paired-device list.
3. Core command `7`, payload `24`.
4. Restart manual pairing with modes `0 -> 2`.

Discovery arrives as async command `0x81`. Address is in payload bytes `9..14`;
name length is little-endian bytes `18..19`; UTF-8 name begins at byte `20`.

## Known limitations

- Pair command `18` and successful paired-list readback are confirmed.
- Battery level is not exposed by firmware `1.4.0`.
- Device-side EQ commands are not exposed; EQ would require a Windows APO such as
  Equalizer APO.
- Brightness remains read-only because the write scale is unknown.
- Firmware update, reboot, factory reset, and mass deletion remain disabled.

## Release status

- 62 unit tests pass.
- `pip check` passes.
- Published unsigned `v0.2.0-beta.1` received a user-side Defender ML detection
  `Trojan:Win32/Wacatac.B!ml`; its binary must not be treated as distributable.
- Portable EXE builds and launches.
- Latest local unsigned portable size is 13,899,966 bytes (approximately 13.26 MiB).
- EXE is unsigned and may trigger SmartScreen.
- Regular CI validates both the unsigned executable and a development MSIX.
- SignPath Foundation rejected the project because it does not yet have enough
  external reputation signals. The release path is now Microsoft Store MSIX;
  Store certification automatically replaces the package signature with a
  Microsoft certificate.
- Store identity from Partner Center is committed in
  `packaging/store_identity.json`; the Store workflow runs on `main` pushes or
  manually and produces an MSIX artifact for Partner Center submission.
- Pairing command `18` is available in the UI and confirmed by paired-list readback.
- A clean Windows 10/11 test without Python is still required.

## Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\hardware_smoke.py
.\.venv\Scripts\python.exe scripts\build_windows.py
.\.venv\Scripts\python.exe -m fiiocontrol
```

## Git state

The GitHub repository was created empty. Files were copied into the new clone and
were still untracked at the last check. Before the first push:

1. Open `C:\Users\denis\Projects\fiio-air-link-control` as the workspace.
2. Read this handoff and `docs/FIIO_AIR_LINK_HANDOFF.md`.
3. Run tests and inspect `git status` and `git diff --check`.
4. Create the initial commit only after reviewing all files.

## Suggested first prompt in the new session

```text
Read docs/SESSION_HANDOFF.md, docs/FIIO_AIR_LINK_HANDOFF.md, and docs/ROADMAP.md.
Verify the repository state and continue preparing FALC for a beta release.
```
