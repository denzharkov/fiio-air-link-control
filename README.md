# FIIO Air Link Control

English | [Русский](README.ru.md)

FIIO Air Link Control (FALC) is an unofficial open-source Windows application for
controlling FIIO Air Link over USB. It provides codec settings, Bluetooth device
management, pairing, and diagnostics without requiring the vendor application.

The application works locally and does not use telemetry, advertising, user
accounts, or cloud services.

## Interface

### Overview

Shows the current Air Link state at a glance:

- firmware and application build;
- active Bluetooth connection and connected headsets;
- enabled codecs and current LDAC/aptX Adaptive modes;
- Bluetooth name and indicator brightness reported by the device.

Use this page to refresh the device state or disconnect the current USB session.
Automatic connection resumes when a new session is started.

### Audio

Controls Bluetooth audio capabilities:

- enable or disable supported codecs;
- select LDAC quality mode;
- select aptX Adaptive quality mode.

Every change is read back from Air Link before the interface reports success.
The codec actually used also depends on the connected receiver and radio
conditions.

### Devices

Manages Bluetooth receivers and headphones:

- view paired devices and their connection state;
- connect or disconnect a paired device;
- start a 60-second discovery session;
- select and pair a newly discovered device.

Air Link must be connected through USB. Put the target receiver into pairing mode
and disconnect it from other Bluetooth sources before starting discovery.

### Diagnostics

Provides information useful for troubleshooting:

- firmware and HID interface details;
- successful requests, timeouts, and I/O errors;
- disconnect and reconnect counters;
- application version and source commit;
- privacy-safe diagnostic JSON export.

Raw packet logging is disabled by default. Diagnostic exports redact packet
payloads and device identifiers.

## Requirements

- Windows 10 or Windows 11, 64-bit;
- Microsoft Edge WebView2 Runtime, normally included with Windows;
- FIIO Air Link connected through USB;
- hardware-tested firmware: `1.4.0`.

## Download

Download the latest `FIIO-Air-Link-Control.exe` and its `.sha256` file from
[GitHub Releases](https://github.com/denzharkov/fiio-air-link-control/releases).
No installation or Python runtime is required.

The executable is currently unsigned, so Microsoft SmartScreen may display a
warning on first launch.

## Language

The interface starts in English. Use the language selector in the header to switch
to Russian. The selection is saved locally for the next launch.

## Development

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m fiiocontrol
```

Build the portable executable with:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py
```

Protocol notes and current limitations are documented in
[`docs/FIIO_AIR_LINK_HANDOFF.md`](docs/FIIO_AIR_LINK_HANDOFF.md). The development
roadmap is available in [`docs/ROADMAP.md`](docs/ROADMAP.md).

FIIO Air Link Control is an independent community project and is not affiliated
with or endorsed by FIIO Electronics Technology Co., Ltd.
