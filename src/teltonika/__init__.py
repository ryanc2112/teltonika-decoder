"""Lightweight, zero-dependency decoder for Teltonika GPS tracker packets."""

from .decoder import (
    CODEC_8,
    CODEC_8E,
    CODEC_12,
    CODEC_13,
    CODEC_14,
    CODEC_16,
    GPS,
    AVLPacket,
    AVLRecord,
    CommandPacket,
    CRCError,
    TeltonikaError,
    UDPPacket,
    crc16_ibm,
    decode,
    decode_imei,
    decode_tcp,
    decode_udp,
    detect,
    encode_command,
    encode_imei_ack,
)
from .io_names import IO_NAMES, io_name
from .output import format_packet, to_dict

__version__ = "0.1.0"

__all__ = [
    "CODEC_8", "CODEC_8E", "CODEC_12", "CODEC_13", "CODEC_14", "CODEC_16",
    "GPS", "AVLPacket", "AVLRecord", "CommandPacket", "UDPPacket",
    "CRCError", "TeltonikaError",
    "crc16_ibm", "decode", "decode_imei", "decode_tcp", "decode_udp", "detect",
    "encode_command", "encode_imei_ack",
    "IO_NAMES", "io_name", "format_packet", "to_dict",
]
