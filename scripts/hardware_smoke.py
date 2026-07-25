from __future__ import annotations

import argparse
import sys

from fiiocontrol.controller import AirLinkController


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe FIIO Air Link hardware smoke test")
    parser.add_argument(
        "--verify-codec-write",
        action="store_true",
        help="write the current codec configuration and verify it with readback",
    )
    parser.add_argument(
        "--verify-quality-write",
        action="store_true",
        help="write currently selected quality modes and verify their readback",
    )
    parser.add_argument(
        "--verify-connection-actions",
        action="store_true",
        help="disconnect one connected receiver and reconnect it in a finally block",
    )
    parser.add_argument(
        "--verify-pairing-mode",
        action="store_true",
        help="enter manual pairing mode and return to stable automatic mode one",
    )
    arguments = parser.parse_args()

    controller = AirLinkController()
    try:
        snapshot = controller.connect()
        state = snapshot.state
        print(f"PASS firmware: {state.firmware}")
        print(f"PASS local name: {state.local_name}")
        print(f"PASS codecs: {state.codecs}")
        print(f"PASS connection: {state.connection_status}")
        print(f"PASS paired devices: {len(state.paired_devices)}")
        print(f"PASS brightness raw: {state.brightness_raw}")

        errors = {name: error for name, error in state.errors.items() if error}
        if errors:
            for name, error in errors.items():
                print(f"FAIL {name}: {error.code}: {error.message}", file=sys.stderr)
            raise SystemExit(1)

        if arguments.verify_codec_write:
            confirmed = controller.set_codecs(dict(state.codecs)).codecs
            if confirmed != state.codecs:
                print("FAIL codec write readback mismatch", file=sys.stderr)
                raise SystemExit(1)
            print("PASS codec write/readback (configuration unchanged)")
        else:
            print("SKIP codec write; pass --verify-codec-write to test confirmed write")

        if arguments.verify_quality_write:
            if state.codecs.get("ldac") and state.ldac_mode is not None:
                confirmed = controller.set_ldac_mode(state.ldac_mode).ldac_mode
                print(f"PASS LDAC mode write/readback: {confirmed}")
            else:
                print("SKIP LDAC mode write; codec is disabled")
            if state.codecs.get("aptxAdaptive") and state.aptx_mode is not None:
                confirmed = controller.set_aptx_mode(state.aptx_mode).aptx_mode
                print(f"PASS aptX Adaptive mode write/readback: {confirmed}")
            else:
                print("SKIP aptX Adaptive mode write; codec is disabled")
        else:
            print(
                "SKIP quality mode writes; pass --verify-quality-write to test "
                "confirmed writes"
            )

        if arguments.verify_connection_actions:
            target = next(
                (item for item in state.paired_devices if item.connected), None
            )
            if target is None:
                print("SKIP connection actions; no connected paired device")
            else:
                try:
                    disconnected = controller.disconnect_paired_device(target.address)
                    confirmed = next(
                        item
                        for item in disconnected.paired_devices
                        if item.address == target.address
                    )
                    if confirmed.connected:
                        raise RuntimeError("disconnect readback mismatch")
                    print("PASS paired-device disconnect/readback")
                finally:
                    connected = controller.connect_paired_device(target.address)
                    restored = next(
                        item
                        for item in connected.paired_devices
                        if item.address == target.address
                    )
                    if not restored.connected:
                        raise RuntimeError("connect restore readback mismatch")
                    print("PASS paired-device connect/readback and restoration")
        else:
            print(
                "SKIP connection actions; pass --verify-connection-actions to "
                "test disconnect/reconnect"
            )

        if arguments.verify_pairing_mode:
            started = controller.start_manual_pairing().pairing_status
            try:
                if started != 2:
                    raise RuntimeError("pairing start readback mismatch")
                print("PASS manual pairing mode/readback: 2")
            finally:
                stopped = controller.stop_manual_pairing().pairing_status
                if stopped != 1:
                    raise RuntimeError("pairing stop readback mismatch")
                print("PASS manual pairing stop/readback: 1")
        else:
            print(
                "SKIP pairing mode write; pass --verify-pairing-mode to test "
                "start/stop"
            )
    finally:
        controller.disconnect()


if __name__ == "__main__":
    main()
