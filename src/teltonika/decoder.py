"""Decode and encode Teltonika device packets.

Supported:
  * IMEI handshake
  * TCP AVL data: Codec 8, Codec 8 Extended (8E), Codec 16
  * UDP AVL data (same codecs, UDP channel header)
  * GPRS commands/responses: Codec 12, 13, 14

Pure standard library. Every multi-byte field is big-endian, as the protocol specifies.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

CODEC_8 = 0x08
CODEC_8E = 0x8E
CODEC_16 = 0x10
CODEC_12 = 0x0C
CODEC_13 = 0x0D
CODEC_14 = 0x0E

AVL_CODECS = {CODEC_8: "8", CODEC_8E: "8E", CODEC_16: "16"}
COMMAND_CODECS = {CODEC_12: "12", CODEC_13: "13", CODEC_14: "14"}

COMMAND_TYPES = {0x05: "command", 0x06: "response", 0x11: "nack"}


class TeltonikaError(ValueError):
    """Raised for malformed, truncated or unsupported packets."""


class CRCError(TeltonikaError):
    """Raised when a TCP packet's CRC-16 does not match its data."""


def crc16_ibm(data: bytes) -> int:
    """CRC-16/IBM (a.k.a. CRC-16/ARC): poly 0xA001 reflected, init 0. Used by TCP packets."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


# --------------------------------------------------------------------------- data model


@dataclass
class GPS:
    longitude: float
    latitude: float
    altitude: int  # metres
    angle: int  # degrees from north
    satellites: int
    speed: int  # km/h

    @property
    def valid(self) -> bool:
        """False when the device had no fix (it reports zero satellites)."""
        return self.satellites > 0


@dataclass
class AVLRecord:
    timestamp: datetime
    priority: int  # 0 low, 1 high, 2 panic
    gps: GPS
    event_io_id: int  # IO element that triggered the record, 0 for periodic records
    total_io: int
    io: Dict[int, Union[int, bytes]] = field(default_factory=dict)
    generation_type: Optional[int] = None  # Codec 16 only


@dataclass
class AVLPacket:
    codec: int
    records: List[AVLRecord]
    crc: Optional[int] = None  # TCP only

    @property
    def codec_name(self) -> str:
        return AVL_CODECS[self.codec]

    def ack(self) -> bytes:
        """The 4-byte reply a server sends over TCP to accept this packet."""
        return struct.pack(">I", len(self.records))


@dataclass
class UDPPacket:
    packet_id: int
    avl_packet_id: int
    imei: str
    avl: AVLPacket

    def ack(self) -> bytes:
        """The UDP reply that accepts every record in this packet."""
        return struct.pack(">HHBBB", 5, self.packet_id, 0x01, self.avl_packet_id, len(self.avl.records))


@dataclass
class CommandPacket:
    codec: int
    type: int  # 0x05 command, 0x06 response, 0x11 nACK (Codec 14)
    payload: bytes
    timestamp: Optional[datetime] = None  # Codec 13 only
    imei: Optional[str] = None  # Codec 14 only
    crc: Optional[int] = None

    @property
    def codec_name(self) -> str:
        return COMMAND_CODECS[self.codec]

    @property
    def type_name(self) -> str:
        return COMMAND_TYPES.get(self.type, f"0x{self.type:02X}")

    @property
    def text(self) -> str:
        return self.payload.decode("ascii", errors="replace")


Packet = Union[str, AVLPacket, UDPPacket, CommandPacket]


# --------------------------------------------------------------------------- reader


class _Reader:
    __slots__ = ("data", "pos")

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.data):
            raise TeltonikaError(
                f"truncated packet: needed {n} byte(s) at offset {self.pos}, "
                f"only {len(self.data) - self.pos} left"
            )
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def uint(self, n: int) -> int:
        return int.from_bytes(self.take(n), "big")

    def i16(self) -> int:
        return struct.unpack(">h", self.take(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.take(4))[0]

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos


def _to_bytes(data: Union[bytes, bytearray, str]) -> bytes:
    if isinstance(data, str):
        cleaned = "".join(data.split())
        if cleaned[:2].lower() == "0x":
            cleaned = cleaned[2:]
        try:
            return bytes.fromhex(cleaned)
        except ValueError as exc:
            raise TeltonikaError(f"not valid hex: {exc}") from None
    return bytes(data)


def _ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


# --------------------------------------------------------------------------- AVL codecs

# (event IO id width, total IO count width, per-size count width, IO id width)
_LAYOUT = {
    CODEC_8: (1, 1, 1, 1),
    CODEC_8E: (2, 2, 2, 2),
    CODEC_16: (2, 1, 1, 2),
}


def _read_record(r: _Reader, codec: int) -> AVLRecord:
    timestamp = _ms_to_datetime(r.uint(8))
    priority = r.uint(1)
    gps = GPS(
        longitude=r.i32() / 1e7,
        latitude=r.i32() / 1e7,
        altitude=r.i16(),
        angle=r.uint(2),
        satellites=r.uint(1),
        speed=r.uint(2),
    )
    event_w, total_w, count_w, id_w = _LAYOUT[codec]
    event_io_id = r.uint(event_w)
    generation_type = r.uint(1) if codec == CODEC_16 else None
    total_io = r.uint(total_w)

    io: Dict[int, Union[int, bytes]] = {}
    for size in (1, 2, 4, 8):
        for _ in range(r.uint(count_w)):
            io_id = r.uint(id_w)
            io[io_id] = r.uint(size)
    if codec == CODEC_8E:
        for _ in range(r.uint(2)):
            io_id = r.uint(2)
            io[io_id] = r.take(r.uint(2))

    return AVLRecord(timestamp, priority, gps, event_io_id, total_io, io, generation_type)


def _read_avl_body(r: _Reader) -> AVLPacket:
    """Codec ID, record count, records, record count again."""
    codec = r.uint(1)
    if codec not in AVL_CODECS:
        raise TeltonikaError(f"unsupported AVL codec 0x{codec:02X}")
    count = r.uint(1)
    records = [_read_record(r, codec) for _ in range(count)]
    count_again = r.uint(1)
    if count != count_again:
        raise TeltonikaError(f"record count mismatch: header says {count}, footer says {count_again}")
    return AVLPacket(codec, records)


def _read_command_body(r: _Reader, end: int) -> CommandPacket:
    codec = r.uint(1)
    r.uint(1)  # quantity 1, always 1
    ctype = r.uint(1)
    size = r.uint(4)
    timestamp = imei = None
    if codec == CODEC_13:
        timestamp = datetime.fromtimestamp(r.uint(4), tz=timezone.utc)
        size -= 4
    elif codec == CODEC_14:
        imei = r.take(8).hex().lstrip("0") or "0"
        size -= 8
    if size < 0:
        raise TeltonikaError("command size field is smaller than its header")
    payload = r.take(size)
    r.uint(1)  # quantity 2
    if r.pos != end:
        raise TeltonikaError(f"{end - r.pos} unexpected byte(s) after command payload")
    return CommandPacket(codec, ctype, payload, timestamp, imei)


# --------------------------------------------------------------------------- public decode API


def decode_imei(data: Union[bytes, str]) -> str:
    """Decode the handshake a device sends first: 2-byte length + ASCII IMEI."""
    raw = _to_bytes(data)
    r = _Reader(raw)
    length = r.uint(2)
    imei = r.take(length)
    if r.remaining:
        raise TeltonikaError(f"{r.remaining} unexpected byte(s) after IMEI")
    if not imei.isdigit():
        raise TeltonikaError("IMEI handshake contains non-digit characters")
    return imei.decode("ascii")


def decode_tcp(data: Union[bytes, str], verify_crc: bool = True) -> Union[AVLPacket, CommandPacket]:
    """Decode a TCP frame: AVL data (Codec 8/8E/16) or a command (Codec 12/13/14)."""
    raw = _to_bytes(data)
    r = _Reader(raw)
    if r.uint(4) != 0:
        raise TeltonikaError("TCP frame must start with a 4-byte zero preamble")
    length = r.uint(4)
    body_start = r.pos
    body = r.take(length)
    crc = r.uint(4)
    if r.remaining:
        raise TeltonikaError(f"{r.remaining} unexpected byte(s) after CRC")
    if verify_crc and crc16_ibm(body) != crc:
        raise CRCError(f"CRC mismatch: packet says 0x{crc:04X}, data gives 0x{crc16_ibm(body):04X}")

    br = _Reader(raw, body_start)
    end = body_start + length
    codec = raw[body_start] if length else None
    if codec in COMMAND_CODECS:
        packet: Union[AVLPacket, CommandPacket] = _read_command_body(br, end)
    else:
        packet = _read_avl_body(br)
        if br.pos != end:
            raise TeltonikaError(f"{end - br.pos} unexpected byte(s) after AVL records")
    packet.crc = crc
    return packet


def decode_udp(data: Union[bytes, str]) -> UDPPacket:
    """Decode a UDP datagram carrying AVL data."""
    raw = _to_bytes(data)
    r = _Reader(raw)
    length = r.uint(2)
    if length != len(raw) - 2:
        raise TeltonikaError(f"UDP length field says {length} byte(s), datagram has {len(raw) - 2}")
    packet_id = r.uint(2)
    r.uint(1)  # not usable byte (0x01)
    avl_packet_id = r.uint(1)
    imei = r.take(r.uint(2)).decode("ascii", errors="replace")
    avl = _read_avl_body(r)
    if r.remaining:
        raise TeltonikaError(f"{r.remaining} unexpected byte(s) after AVL records")
    return UDPPacket(packet_id, avl_packet_id, imei, avl)


def detect(data: Union[bytes, str]) -> str:
    """Guess what a raw frame is: 'tcp', 'udp' or 'imei'."""
    raw = _to_bytes(data)
    if len(raw) >= 12 and raw[:4] == b"\x00\x00\x00\x00":
        return "tcp"
    if len(raw) >= 2 and int.from_bytes(raw[:2], "big") == len(raw) - 2:
        if raw[2:].isdigit():
            return "imei"
        if len(raw) >= 8:
            imei_len = int.from_bytes(raw[6:8], "big")
            if raw[8:8 + imei_len].isdigit():
                return "udp"
    raise TeltonikaError("could not recognise frame as TCP, UDP or IMEI handshake")


def decode(data: Union[bytes, str], verify_crc: bool = True) -> Packet:
    """Decode any frame. Returns an IMEI string, AVLPacket, UDPPacket or CommandPacket."""
    raw = _to_bytes(data)
    kind = detect(raw)
    if kind == "tcp":
        return decode_tcp(raw, verify_crc)
    if kind == "udp":
        return decode_udp(raw)
    return decode_imei(raw)


# --------------------------------------------------------------------------- encoders


def _tcp_frame(body: bytes) -> bytes:
    return b"\x00\x00\x00\x00" + struct.pack(">I", len(body)) + body + struct.pack(">I", crc16_ibm(body))


def encode_command(command: Union[str, bytes], imei: Optional[str] = None) -> bytes:
    """Build a server-to-device GPRS command.

    Codec 12 by default; pass ``imei`` to build a Codec 14 command, which the
    device only executes when the IMEI matches its own.
    """
    payload = command.encode("ascii") if isinstance(command, str) else bytes(command)
    if imei is None:
        body = bytes([CODEC_12, 1, 0x05]) + struct.pack(">I", len(payload)) + payload + b"\x01"
    else:
        if not imei.isdigit() or len(imei) > 16:
            raise TeltonikaError("IMEI must be up to 16 digits")
        imei_bytes = bytes.fromhex(imei.rjust(16, "0"))
        body = (
            bytes([CODEC_14, 1, 0x05])
            + struct.pack(">I", len(payload) + 8)
            + imei_bytes
            + payload
            + b"\x01"
        )
    return _tcp_frame(body)


def encode_imei_ack(accept: bool = True) -> bytes:
    """The 1-byte reply to an IMEI handshake: 0x01 accept, 0x00 reject."""
    return b"\x01" if accept else b"\x00"
