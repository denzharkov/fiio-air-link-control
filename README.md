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
<img width="1077" height="908" alt="Screenshot_5" src="https://github.com/user-attachments/assets/38e3d216-f7db-48e4-80d0-b238b57cd433" />

- firmware and application build;
- active Bluetooth connection and connected headsets;
- enabled codecs and current LDAC/aptX Adaptive modes;
- Bluetooth name and indicator brightness reported by the device.

Use this page to refresh the device state or disconnect the current USB session.
Automatic connection resumes when a new session is started.

### Audio

Controls Bluetooth audio capabilities:
<img width="1077" height="908" alt="Screenshot_1" src="https://github.com/user-attachments/assets/c2388f85-5379-43af-8d22-f0d2ab0afc54" />

- enable or disable supported codecs;
- select LDAC quality mode;
- select aptX Adaptive quality mode.

Every change is read back from Air Link before the interface reports success.
The codec actually used also depends on the connected receiver and radio
conditions.

### Devices

Manages Bluetooth receivers and headphones:
<img width="1076" height="906" alt="Screenshot_2" src="https://github.com/user-attachments/assets/ae19d91c-361f-4daf-95cd-346c89f96288" />

- view paired devices and their connection state;
- connect or disconnect a paired device;
- start a 60-second discovery session;
- select and pair a newly discovered device.

Air Link must be connected through USB. Put the target receiver into pairing mode
and disconnect it from other Bluetooth sources before starting discovery.

### Diagnostics

Provides information useful for troubleshooting:
<img width="1074" height="908" alt="Screenshot_3" src="https://github.com/user-attachments/assets/7e3a4a69-c87b-4ac9-837e-eb821a637cc8" />

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

FIIO Air Link Control is an independent community project and is not affiliated
with or endorsed by FIIO Electronics Technology Co., Ltd.
