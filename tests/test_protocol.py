import unittest

from fiiocontrol.device import encode_name
from fiiocontrol.protocol import encode_packet, parse_packet


class ProtocolTests(unittest.TestCase):
    def test_encodes_request_packets(self) -> None:
        self.assertEqual(
            encode_packet(0, 5),
            bytes((0xFF, 0x03, 0, 0, 0, 0x1D, 0, 5)),
        )
        self.assertEqual(
            encode_packet(24, 7, (3, 8, 1, 0)),
            bytes((0xFF, 0x03, 0, 4, 0, 0x1D, 0x30, 7, 3, 8, 1, 0)),
        )

    def test_rejects_invalid_packet_fields(self) -> None:
        with self.assertRaises(ValueError):
            encode_packet(128, 5)
        with self.assertRaises(ValueError):
            encode_packet(0, 256)
        with self.assertRaises(ValueError):
            encode_packet(0, 5, bytes(256))

    def test_parses_payload_and_validates_header(self) -> None:
        packet = parse_packet(encode_packet(24, 6, (3, 8)) + b"ignored")
        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet.feature_byte, 0x30)
        self.assertEqual(packet.command, 6)
        self.assertEqual(packet.payload, b"\x03\x08")
        self.assertIsNone(parse_packet(b"\xff\x03\x00"))
        self.assertIsNone(
            parse_packet(bytes((0xFF, 0x03, 0, 2, 0, 0x1D, 0x30, 6, 3)))
        )
        self.assertIsNone(parse_packet(bytes((0xFF, 0x03, 0, 0, 0, 0, 0, 5))))

    def test_truncates_name_at_complete_utf8_character(self) -> None:
        self.assertEqual(encode_name("a" * 31 + "я"), b"a" * 31)
        exact = encode_name("a" * 30 + "я")
        self.assertEqual(len(exact), 32)
        self.assertEqual(exact.decode("utf-8"), "a" * 30 + "я")


if __name__ == "__main__":
    unittest.main()
