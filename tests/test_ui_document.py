import unittest

from fiiocontrol.controller import ConnectionSnapshot
from fiiocontrol.build_info import BuildInfo
from fiiocontrol.capabilities import capabilities_for_firmware
from fiiocontrol.device import AirLinkState, ConnectionStatus, DiscoveredDevice, PairedDevice
from fiiocontrol.hid_backend import HidDescriptor
from fiiocontrol.lifecycle import ConnectionPhase
from fiiocontrol.ui_document import build_document


class UiDocumentTests(unittest.TestCase):
    def test_builds_disconnected_action_document(self) -> None:
        document = build_document(
            snapshot=None,
            status="offline",
            status_tone="muted",
        )

        self.assertEqual(document["schema"], "fiiocontrol.bdui/v1")
        self.assertEqual(document["footer"]["badge"]["value"], "OFFLINE")
        language = document["header"]["children"][2]
        self.assertEqual(language["type"], "select")
        self.assertEqual(language["value"], "en")
        self.assertEqual(language["action"], "set_language")
        self.assertEqual(document["content"]["type"], "hero")
        self.assertEqual(document["content"]["action"]["action"], "connect")

    def test_builds_reconnecting_document(self) -> None:
        document = build_document(
            snapshot=None,
            status="Ожидание повторного подключения",
            status_tone="warning",
            phase=ConnectionPhase.RECONNECTING,
            revision=4,
        )

        self.assertEqual(document["revision"], 4)
        self.assertEqual(document["footer"]["badge"]["value"], "RECONNECTING")
        self.assertEqual(document["content"]["action"]["action"], "connect")

    def test_separates_overview_audio_and_device_pages(self) -> None:
        state = AirLinkState(
            firmware="1.4.0",
            local_name="FIIO Air Link",
            codecs={
                "aptX": False,
                "aptXLL": False,
                "aptXHD": False,
                "aptxAdaptive": False,
                "ldac": True,
            },
            ldac_mode=0,
            pairing_status=0,
            connection_status=ConnectionStatus(True, 1, 0),
            paired_devices=[
                PairedDevice(
                    address=(1, 2, 3, 4, 5, 6),
                    connected=True,
                    connect_type=2,
                    profiles=(1, 0, 0, 0),
                    name="Receiver",
                )
            ],
            brightness_raw=7,
        )
        snapshot = ConnectionSnapshot(
            "FIIO Air Link",
            state,
            HidDescriptor(
                path=b"path",
                product_string="FIIO Air Link",
                manufacturer_string="FIIO",
                serial_number=None,
                interface_number=1,
                usage_page=0xFF00,
                usage=3,
            ),
            capabilities_for_firmware("1.4.0"),
        )
        document = build_document(
            snapshot=snapshot,
            status="Air Link 1.4.0",
            status_tone="success",
            phase=ConnectionPhase.CONNECTED,
            build_info=BuildInfo("0.2.0", "0123456789abcdef", False),
        )

        self.assertEqual(document["footer"]["badge"]["value"], "CONNECTED")
        navigation = document["header"]["children"][1]["children"]
        self.assertEqual(
            [item["action"] for item in navigation],
            ["show_overview", "show_audio", "show_devices", "show_diagnostics"],
        )
        overview_grid = document["content"]["children"][1]
        self.assertEqual(
            [item["title"] for item in overview_grid["children"]],
            ["Подключение", "Аудио", "Устройство", "Система"],
        )

        audio_document = build_document(
            snapshot=snapshot,
            status="connected",
            status_tone="success",
            view="audio",
        )
        audio_grid = audio_document["content"]["children"][1]
        codec_card = audio_grid["children"][0]
        codec_form = codec_card["children"][0]
        self.assertEqual(codec_form["type"], "form")
        self.assertEqual(codec_form["submit"]["action"], "set_codecs")
        modes_card = audio_grid["children"][1]
        segmented = [
            child for child in modes_card["children"] if child.get("type") == "segmented"
        ]
        self.assertEqual(len(segmented), 2)
        self.assertEqual(segmented[0]["action"], "set_aptx_mode")
        self.assertTrue(segmented[0]["disabled"])
        self.assertEqual(segmented[1]["action"], "set_ldac_mode")
        self.assertFalse(segmented[1]["disabled"])

        devices_document = build_document(
            snapshot=snapshot,
            status="connected",
            status_tone="success",
            view="devices",
        )
        pairing_card = devices_document["content"]["children"][1]
        pairing_action = next(
            child
            for child in pairing_card["children"]
            if child.get("action") == "start_pairing"
        )
        self.assertEqual(pairing_action["label"], "Добавить новое устройство")
        devices = devices_document["content"]["children"][2]
        self.assertEqual(devices["title"], "Сопряжённые устройства")
        self.assertEqual(devices["children"][0]["type"], "row")
        device_actions = devices["children"][0]["children"][1]["children"]
        self.assertEqual(device_actions[1]["action"], "disconnect_paired_device")
        self.assertEqual(device_actions[1]["payload"]["address"], [1, 2, 3, 4, 5, 6])

    def test_builds_diagnostic_tabs_and_packet_table(self) -> None:
        document = build_document(
            snapshot=None,
            status="offline",
            status_tone="muted",
            view="diagnostics",
            diagnostics={
                "debug": True,
                "last_success_at": "2026-07-25T12:00:00Z",
                "counters": {"requests": 2, "responses": 1},
                "records": [
                    {
                        "timestamp": "2026-07-25T12:00:00Z",
                        "category": "response",
                        "report_id": 8,
                        "feature_byte": 1,
                        "command": 5,
                        "payload_length": 5,
                        "packet": "ff 03",
                    }
                ],
            },
        )

        self.assertEqual(document["content"]["children"][1]["type"], "tabs")
        tabs = document["content"]["children"][1]["tabs"]
        self.assertEqual([tab["label"] for tab in tabs], ["Сводка", "Пакеты"])
        self.assertEqual(tabs[1]["content"]["type"], "table")

    def test_builds_discovered_device_pair_action(self) -> None:
        state = AirLinkState(firmware="1.4.0")
        document = build_document(
            snapshot=ConnectionSnapshot(
                "FIIO Air Link",
                state,
                capabilities=capabilities_for_firmware("1.4.0"),
            ),
            status="pairing",
            status_tone="warning",
            view="devices",
            pairing_active=True,
            discovered_devices=(
                DiscoveredDevice((1, 2, 3, 4, 5, 6), "Buds"),
            ),
        )

        discovered_card = document["content"]["children"][2]
        self.assertEqual(discovered_card["title"], "Найденные устройства")
        action = discovered_card["children"][0]["children"][1]
        self.assertEqual(action["action"], "pair_discovered_device")
        self.assertEqual(action["payload"]["address"], [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
