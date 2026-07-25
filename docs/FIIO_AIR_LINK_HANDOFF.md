# FIIO Air Link protocol and implementation notes

## Scope

This repository is a FIIO Air Link-only Windows application. The current
implementation uses Python, Backend-Driven UI rendered by `pywebview`/WebView2,
and the `hidapi` package. It does not use Node.js, Electron, or WebHID.

Keep generic FIIO PEQ commands and drivers for JA11/BTR17 out of this project.
Air Link uses a separate Qualcomm/GigaWiT-style protocol.

## Hardware identity

- Product: FIIO Air Link
- Firmware tested on hardware: `1.4.0`
- USB vendor ID: `0x2972` (`10610`)
- USB product ID: `0x0158` (`344`)
- HID output report ID: `7`, payload size 446 bytes
- HID input report ID: `8`, payload size 446 bytes
- Additional HID input report ID: `9`, payload size 11 bytes

Windows exposes several HID interfaces for this VID/PID. The control collection
is usage page `0xFF00`, usage `3`, interface `1`. `AirLinkController.connect()`
selects that collection and verifies it with the safe firmware GET command. Never
assume the first enumerated path is the control interface.

## Confirmed behavior

Confirmed on real hardware:

- report ID `7` connection;
- firmware GET returning `1.4.0`;
- codec set GET;
- codec set SET followed by readback.
- LDAC mode SET `1 → 2 → 1` with GET readback and restoration;
- aptX Adaptive mode SET `19 → 3 → 19` with GET readback and restoration.
- paired-device disconnect command `17` with list/status readback;
- paired-device connect command `16` with list/status readback and restoration.
- pairing restart sequence `0 → 2` and stable stop transition `2 → 1`.
- pair command `18` with event `0x83` and paired-list readback.

Still unconfirmed:

- Bluetooth name SET;
- delete action;
- reboot and factory reset.

Brightness GET returns raw value `7`. Writes of `100`, `50`, and `30` did not
change the indicator. The range and SET payload remain unresolved, so the UI
keeps brightness read-only.

Notification handshake confirmed from FIIO Control 4.3.1 and real hardware:

1. Send core feature command `8`, payload `24`.
2. Read pairing status and paired-device list.
3. Send core feature command `7`, payload `24`.
4. Switch pairing mode `0 → 2` for manual discovery.

After this handshake firmware `1.4.0` emitted async commands `0x81`, `0x83`,
`0x84`, and `0x85` over input report `8`. An empty feature-24 command `24` is
incorrect and times out.

Discovery command `0x81` payload:

```text
bytes 9..14    Bluetooth address
bytes 18..19   little-endian name length including terminator
bytes 20...    UTF-8 name without the final terminator
```

Pairing uses command `18` with payload `0, ...address, 0`, followed by paired-list
GET polling and event `0x83`. Discovery entries expire after 15 seconds, matching
FIIO Control. A pair attempt is asynchronous and has its own 15-second deadline;
it does not block the lifecycle worker or reuse the overall search timeout.
Mode `0` is only a transient scan reset and does not remain stable after manual
search has started. Pairing therefore returns to stable automatic mode `1` on
cancel, timeout, disconnect, or application shutdown.

## Packet format

Requests and responses use this header:

```text
FF 03 00 LL 00 1D FF CC [payload...]
```

| Offset | Meaning |
|---:|---|
| `0` | `0xFF` |
| `1` | `0x03` |
| `2` | `0x00` |
| `3` | payload length |
| `4` | `0x00` |
| `5` | `0x1D` |
| `6` | feature shifted left by one |
| `7` | command |
| `8...` | payload |

Features:

- Core: `0`
- App GigaWiT: `24`, encoded as `0x30`

Firmware query, feature `0`, command `5`:

```text
FF 03 00 00 00 1D 00 05
```

The Python transport prepends output report ID `7`, pads the report to 446 bytes,
and reads input report ID `8` (or the short event report `9`). Responses set the
low bit of the encoded feature, so request feature `24` (`0x30`) is matched to
response feature byte `0x31`. Commands are serialized with one lock. Other valid
packets are routed as notifications.

## Command reference

Commands below use feature `24` unless marked as core.

| Operation | GET | SET/action | Payload |
|---|---:|---:|---|
| Firmware version | core `5` | - | empty |
| Local Bluetooth name | `0` | `1` | UTF-8, maximum 32 bytes |
| Bluetooth codec set | `6` | `7` | codec IDs followed by `1, 0` |
| Pairing status | `10` | `11` | one status byte |
| Connected status | `12` | - | empty |
| Paired-device list | `14` | - | empty |
| Remote device name | `15` | - | `0, ...address, 0` |
| Connect device | - | `16` | `0, ...address, 0` |
| Disconnect device | - | `17` | `0, ...address, 0` |
| Pair device | - | `18` | `0, ...address, 0` |
| Delete paired device | - | `19` | `0, ...address, 0` |
| Delete all paired devices | - | `20` | empty |
| aptX mode | `64` | `65` | one mode byte |
| LDAC mode | `66` | `67` | one mode byte |
| Indicator brightness | `82` | `83` | unresolved raw byte |
| Delete all settings | - | `121` | empty |
| Reboot | - | `122` | empty |

Core handshake commands `8` and `7` both use one-byte payload `24`; they are not
feature-24 command `24`.

### Codec IDs

| Codec | ID |
|---|---:|
| SBC | `1` |
| aptX | `3` |
| aptX Low Latency | `5` |
| aptX HD | `6` |
| aptX Adaptive | `7` |
| LDAC | `8` |
| LHDC | `9` |

The UI exposes aptX, aptX Low Latency, aptX HD, aptX Adaptive, and LDAC. A SET
payload is `enabled codec IDs + [1, 0]`. Every write must be followed by GET `6`;
success is reported only after exact readback.

### Quality modes

aptX Adaptive:

| Mode | Value |
|---|---:|
| Low latency | `2` |
| High quality | `3` |
| Lossless | `19` |

LDAC:

| Mode | Value | Expected bitrate family |
|---|---:|---|
| HQ | `0` | 990/909 kbps |
| SQ | `1` | 660/606 kbps |
| MQ | `2` | 330/303 kbps |

These values are writable on firmware `1.4.0`. The UI exposes direct controls
only while the corresponding codec is enabled. Every SET is followed by its
property-specific GET and a strict value comparison.

### Connection and paired devices

Connection status payload:

```text
byte 0  connected flag (1 means connected)
byte 1  connected headset count
byte 2  connected LE device count
```

Paired-device list starts with a count. Each item occupies 12 bytes:

```text
byte 0       connection type
bytes 1..6   Bluetooth address
byte 7       connected flag; 0x80 means connected
bytes 8..11  supported profile flags
```

Entries with four zero profile bytes are ignored. Remote-name GET and future
connect/disconnect operations use payload `0, ...six address bytes, 0`.

## Safety rules

- Keep all HID requests serialized.
- Do not treat an unrelated valid packet as the current response.
- Preserve the last confirmed value when an optional GET fails.
- Do not retry destructive commands automatically.
- Verify every SET with a property-specific GET.
- Keep unverified writes and destructive operations out of the UI.
- Do not implement firmware update until the full update and recovery protocol
  is understood.
- Never sweep all possible brightness values.

## Source layout

- `fiiocontrol/protocol.py`: packet framing and parsing.
- `fiiocontrol/transport.py`: serialized writes, background HID reader, response matching, and notification routing.
- `fiiocontrol/hid_backend.py`: `hidapi` enumeration and device wrapper.
- `fiiocontrol/device.py`: command model, parsers, refresh, codec write.
- `fiiocontrol/controller.py`: interface probing and connection lifecycle.
- `fiiocontrol/lifecycle.py`: auto-connect, reconnect, and lifecycle state machine.
- `fiiocontrol/capabilities.py`: firmware-gated feature policy.
- `fiiocontrol/build_info.py`: source and packaged build provenance.
- `fiiocontrol/diagnostics.py`: transport metrics, bounded packet log, and privacy-safe export.
- `fiiocontrol/app.py`: BDUI action dispatcher and WebView lifecycle.
- `fiiocontrol/ui_document.py`: declarative UI document builder.
- `fiiocontrol/web/`: generic BDUI renderer and visual theme.
- `tests/`: protocol, transport, and device unit tests.
- `scripts/hardware_smoke.py`: safe real-device validation.

## Testing

Run unit tests without hardware:

```powershell
python -m unittest discover -s tests -v
```

Hardware smoke test on firmware `1.4.0`:

1. Connect and verify firmware.
2. Read every supported property.
3. Toggle one codec and verify readback.
4. Restore the original codec configuration.
5. Unplug during a GET and verify clean error handling.
6. Reconnect without restarting the application.

Stop before testing any unconfirmed write or destructive operation.
