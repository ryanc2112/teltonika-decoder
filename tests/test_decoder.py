"""Tests use the sample packets published in Teltonika's protocol documentation,
plus synthetic packets built here to cover negative coordinates and Codec 8E NX
(variable-length) IO elements."""

import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

import teltonika as t
from teltonika.cli import main

CODEC8_A = ("000000000000003608010000016B40D8EA30010000000000000000000000000000000105021503010101425E0F01F1"
            "0000601A014E0000000000000000010000C7CF")
CODEC8_B = "000000000000002808010000016B40D9AD80010000000000000000000000000000000103021503010101425E100000010000F22A"
CODEC8E = ("000000000000004A8E010000016B412CEE000100000000000000000000000000000000010005000100010100010011001D0001"
           "0010015E2C880002000B000000003544C87A000E000000001DD7E06A00000100002994")
CODEC16 = ("000000000000005F10020000016BDBC7833000000000000000000000000000000000000B05040200010000030002000B0027"
           "0042563A00000000016BDBC7871800000000000000000000000000000000000B05040200010000030002000B00260042563A"
           "00000200005FB3")
CODEC12_CMD = "000000000000000F0C010500000007676574696E666F0100004312"
CODEC12_RESP = ("00000000000000900C010600000088494E493A323031392F372F323220373A3232205254433A323031392F372F323220373A"
                "3533205253543A32204552523A312053523A302042523A302043463A302046473A3020464C3A302054553A302F302055543A"
                "3020534D533A30204E4F4750533A303A3330204750533A31205341543A302052533A332052463A36352053463A31204D443A"
                "30010000C78F")
UDP_CODEC8 = ("003DCAFE0105000F33353230393330383634303336353508010000016B4F815B300100000000000000000000000000000001"
              "03021503010101425E10000001")
IMEI_HANDSHAKE = "000F333536333037303432343431303133"


def tcp_frame(body: bytes) -> bytes:
    return b"\x00" * 4 + struct.pack(">I", len(body)) + body + struct.pack(">I", t.crc16_ibm(body))


def synthetic_8e() -> bytes:
    """One Codec 8E record in London (negative longitude), with an NX element."""
    ts = int(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc).timestamp() * 1000)
    rec = struct.pack(">QBiihHBH", ts, 1, -1276000, 515000000, -12, 270, 9, 48)
    rec += struct.pack(">HH", 239, 3)  # event IO 239, 3 IO elements in total
    rec += struct.pack(">H", 1) + struct.pack(">HB", 239, 1)  # N1
    rec += struct.pack(">H", 0)  # N2
    rec += struct.pack(">H", 1) + struct.pack(">HI", 16, 123456)  # N4
    rec += struct.pack(">H", 0)  # N8
    rec += struct.pack(">H", 1) + struct.pack(">HH", 385, 3) + b"\xAA\xBB\xCC"  # NX
    return tcp_frame(b"\x8E\x01" + rec + b"\x01")


class TestAVL(unittest.TestCase):
    def test_codec8(self):
        p = t.decode(CODEC8_A)
        self.assertEqual(p.codec, t.CODEC_8)
        self.assertEqual(len(p.records), 1)
        r = p.records[0]
        self.assertEqual(r.timestamp, datetime(2019, 6, 10, 10, 4, 46, tzinfo=timezone.utc))
        self.assertEqual(r.priority, 1)
        self.assertEqual(r.event_io_id, 1)
        self.assertEqual(r.total_io, 5)
        self.assertEqual(r.io, {21: 3, 1: 1, 66: 0x5E0F, 241: 0x601A, 78: 0})
        self.assertEqual(p.ack(), b"\x00\x00\x00\x01")

    def test_codec8_second_sample(self):
        self.assertEqual(t.decode(CODEC8_B).records[0].io, {21: 3, 1: 1, 66: 0x5E10})

    def test_codec8e(self):
        p = t.decode(CODEC8E)
        self.assertEqual(p.codec, t.CODEC_8E)
        self.assertEqual(p.records[0].io, {1: 1, 17: 0x1D, 16: 0x015E2C88, 11: 0x3544C87A, 14: 0x1DD7E06A})

    def test_codec16(self):
        p = t.decode(CODEC16)
        self.assertEqual(p.codec, t.CODEC_16)
        self.assertEqual(len(p.records), 2)
        self.assertEqual(p.records[0].generation_type, 5)
        self.assertEqual(p.records[0].event_io_id, 11)
        self.assertEqual(p.records[1].io[11], 0x26)
        self.assertEqual(p.ack(), b"\x00\x00\x00\x02")

    def test_negative_coordinates_and_nx(self):
        r = t.decode(synthetic_8e()).records[0]
        self.assertAlmostEqual(r.gps.longitude, -0.1276)
        self.assertAlmostEqual(r.gps.latitude, 51.5)
        self.assertEqual(r.gps.altitude, -12)
        self.assertEqual((r.gps.angle, r.gps.satellites, r.gps.speed), (270, 9, 48))
        self.assertTrue(r.gps.valid)
        self.assertEqual(r.io, {239: 1, 16: 123456, 385: b"\xAA\xBB\xCC"})

    def test_udp(self):
        p = t.decode(UDP_CODEC8)
        self.assertIsInstance(p, t.UDPPacket)
        self.assertEqual(p.imei, "352093086403655")
        self.assertEqual(p.packet_id, 0xCAFE)
        self.assertEqual(p.avl_packet_id, 5)
        self.assertEqual(p.avl.records[0].io, {21: 3, 1: 1, 66: 0x5E10})
        self.assertEqual(p.ack().hex().upper(), "0005CAFE010501")


class TestCommands(unittest.TestCase):
    def test_codec12_command(self):
        p = t.decode(CODEC12_CMD)
        self.assertEqual((p.codec, p.type_name, p.text), (t.CODEC_12, "command", "getinfo"))

    def test_codec12_response(self):
        p = t.decode(CODEC12_RESP)
        self.assertEqual(p.type_name, "response")
        self.assertTrue(p.text.startswith("INI:2019/7/22 7:22 RTC:"))

    def test_encode_codec12_matches_docs(self):
        self.assertEqual(t.encode_command("getinfo").hex().upper(), CODEC12_CMD)

    def test_codec14_round_trip(self):
        p = t.decode(t.encode_command("getver", imei="352093081452251"))
        self.assertEqual((p.codec, p.imei, p.text), (t.CODEC_14, "352093081452251", "getver"))

    def test_codec13(self):
        body = b"\x0D\x01\x05" + struct.pack(">I", 4 + 5) + struct.pack(">I", 1_700_000_000) + b"hello" + b"\x01"
        p = t.decode(tcp_frame(body))
        self.assertEqual(p.text, "hello")
        self.assertEqual(p.timestamp, datetime.fromtimestamp(1_700_000_000, tz=timezone.utc))


class TestHandshakeAndErrors(unittest.TestCase):
    def test_imei(self):
        self.assertEqual(t.decode(IMEI_HANDSHAKE), "356307042441013")
        self.assertEqual(t.encode_imei_ack(), b"\x01")

    def test_hex_with_spaces_and_bytes(self):
        spaced = " ".join(CODEC8_B[i:i + 2] for i in range(0, len(CODEC8_B), 2))
        self.assertEqual(t.decode(spaced), t.decode(bytes.fromhex(CODEC8_B)))

    def test_bad_crc(self):
        bad = CODEC8_B[:-4] + "0000"
        with self.assertRaises(t.CRCError):
            t.decode(bad)
        self.assertEqual(len(t.decode(bad, verify_crc=False).records), 1)

    def test_truncated(self):
        with self.assertRaises(t.TeltonikaError):
            t.decode_tcp(CODEC8_A[:-20])

    def test_garbage(self):
        for junk in ("", "zz", "DEADBEEF"):
            with self.assertRaises(t.TeltonikaError):
                t.decode(junk)

    def test_crc16_check_value(self):
        self.assertEqual(t.crc16_ibm(b"123456789"), 0xBB3D)  # CRC-16/ARC check value


class TestOutput(unittest.TestCase):
    def test_json_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["--json", CODEC8E]), 0)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["codec"], "8E")
        self.assertEqual(d["records"][0]["io"]["16"], 0x015E2C88)

    def test_text_output_names_io(self):
        text = t.format_packet(t.decode(synthetic_8e()))
        self.assertIn("Ignition", text)
        self.assertIn("AABBCC", text)

    def test_cli_encode(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--command", "getinfo"])
        self.assertEqual(buf.getvalue().strip(), CODEC12_CMD)

    def test_cli_error_exit_code(self):
        self.assertEqual(main(["DEADBEEF"]), 1)


if __name__ == "__main__":
    unittest.main()
