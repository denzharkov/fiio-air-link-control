import unittest

from fiiocontrol.diagnostics import AirLinkDiagnostics
from fiiocontrol.protocol import encode_packet, parse_packet


class DiagnosticsTests(unittest.TestCase):
    def test_counts_events_without_storing_raw_packets(self) -> None:
        diagnostics = AirLinkDiagnostics(debug=False, capacity=2)
        packet = encode_packet(24, 6, (3, 8))

        diagnostics.record_packet("request", 7, packet)
        diagnostics.record_packet("response", 8, packet)
        diagnostics.increment("timeout")
        diagnostics.increment("disconnect")

        snapshot = diagnostics.snapshot()
        self.assertEqual(snapshot["counters"]["requests"], 1)
        self.assertEqual(snapshot["counters"]["responses"], 1)
        self.assertEqual(snapshot["counters"]["timeouts"], 1)
        self.assertEqual(snapshot["counters"]["disconnects"], 1)
        self.assertIsNotNone(snapshot["last_success_at"])
        self.assertEqual(snapshot["records"], [])

    def test_uses_bounded_development_packet_buffer(self) -> None:
        diagnostics = AirLinkDiagnostics(debug=True, capacity=2)
        for command in (5, 6, 12):
            packet = encode_packet(24, command, (1, 2, 3))
            diagnostics.record_packet(
                "response", 8, packet, parse_packet(packet)
            )

        records = diagnostics.snapshot()["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual([record["command"] for record in records], [6, 12])
        self.assertIn("packet", records[0])

    def test_redacts_all_payload_bytes_in_export(self) -> None:
        diagnostics = AirLinkDiagnostics(debug=True)
        packet = encode_packet(24, 15, (0, 1, 2, 3, 4, 5, 6, 0))
        diagnostics.record_packet("request", 7, packet, parse_packet(packet))

        exported = diagnostics.export_snapshot()
        record = exported["records"][0]
        self.assertTrue(record["packet"].endswith("** ** ** ** ** ** ** **"))
        self.assertNotIn("00 01 02 03 04 05 06 00", record["packet"])
        self.assertNotIn("sha256", record)
        self.assertIn("payload bytes are redacted", exported["privacy"])

    def test_keeps_malformed_metadata_without_raw_data_in_normal_mode(self) -> None:
        diagnostics = AirLinkDiagnostics(debug=False)
        diagnostics.record_packet("malformed", 8, b"private bytes")

        records = diagnostics.snapshot()["records"]
        self.assertEqual(len(records), 1)
        self.assertNotIn("packet", records[0])
        self.assertNotIn("sha256", records[0])


if __name__ == "__main__":
    unittest.main()
