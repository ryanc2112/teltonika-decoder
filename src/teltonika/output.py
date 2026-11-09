"""Turn decoded packets into JSON-ready dicts or readable text."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List

from .decoder import AVLPacket, AVLRecord, CommandPacket, Packet, UDPPacket
from .io_names import io_name


def _record_dict(rec: AVLRecord) -> dict:
    d = {
        "timestamp": rec.timestamp.isoformat().replace("+00:00", "Z"),
        "priority": rec.priority,
        "gps": {
            "latitude": rec.gps.latitude,
            "longitude": rec.gps.longitude,
            "altitude": rec.gps.altitude,
            "angle": rec.gps.angle,
            "satellites": rec.gps.satellites,
            "speed": rec.gps.speed,
            "valid": rec.gps.valid,
        },
        "event_io_id": rec.event_io_id,
        "total_io": rec.total_io,
        "io": {str(k): (v.hex().upper() if isinstance(v, bytes) else v) for k, v in rec.io.items()},
    }
    if rec.generation_type is not None:
        d["generation_type"] = rec.generation_type
    return d


def _avl_dict(p: AVLPacket) -> dict:
    d = {"type": "avl", "codec": p.codec_name, "records": [_record_dict(r) for r in p.records]}
    if p.crc is not None:
        d["crc"] = f"{p.crc:04X}"
    d["ack"] = p.ack().hex().upper()
    return d


def to_dict(packet: Packet) -> dict:
    """A JSON-serialisable view of any decoded packet."""
    if isinstance(packet, str):
        return {"type": "imei", "imei": packet, "ack": "01"}
    if isinstance(packet, UDPPacket):
        d = _avl_dict(packet.avl)
        d.update(type="udp_avl", packet_id=packet.packet_id, avl_packet_id=packet.avl_packet_id,
                 imei=packet.imei, ack=packet.ack().hex().upper())
        return d
    if isinstance(packet, AVLPacket):
        return _avl_dict(packet)
    if isinstance(packet, CommandPacket):
        d: dict[str, Any] = {"type": "command", "codec": packet.codec_name,
                             "command_type": packet.type_name, "text": packet.text,
                             "payload_hex": packet.payload.hex().upper()}
        if packet.timestamp:
            d["timestamp"] = packet.timestamp.isoformat().replace("+00:00", "Z")
        if packet.imei:
            d["imei"] = packet.imei
        if packet.crc is not None:
            d["crc"] = f"{packet.crc:04X}"
        return d
    raise TypeError(f"not a decoded packet: {type(packet).__name__}")


def _fmt_time(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_records(records: List[AVLRecord]) -> List[str]:
    lines = []
    for i, rec in enumerate(records, 1):
        g = rec.gps
        lines.append(f"#{i}  {_fmt_time(rec.timestamp)}  priority {rec.priority}"
                     + (f"  generation {rec.generation_type}" if rec.generation_type is not None else ""))
        fix = "" if g.valid else "  (no fix)"
        lines.append(f"    GPS  {g.latitude:.7f}, {g.longitude:.7f}  alt {g.altitude} m  "
                     f"angle {g.angle} deg  sats {g.satellites}  speed {g.speed} km/h{fix}")
        lines.append(f"    event IO {rec.event_io_id}  |  {rec.total_io} IO element(s)")
        for io_id, value in rec.io.items():
            shown = value.hex().upper() if isinstance(value, bytes) else value
            lines.append(f"    {io_id:>5}  {io_name(io_id):<22} {shown}")
    return lines


def format_packet(packet: Packet) -> str:
    """Human-readable multi-line description of any decoded packet."""
    if isinstance(packet, str):
        return f"IMEI handshake  {packet}\nreply  01 (accept)"
    if isinstance(packet, UDPPacket):
        p = packet.avl
        head = (f"UDP | Codec {p.codec_name} | {len(p.records)} record(s) | IMEI {packet.imei} | "
                f"packet id 0x{packet.packet_id:04X} | AVL packet id {packet.avl_packet_id}")
        return "\n".join([head, *_fmt_records(p.records), f"reply  {packet.ack().hex().upper()}"])
    if isinstance(packet, AVLPacket):
        head = f"TCP | Codec {packet.codec_name} | {len(packet.records)} record(s) | CRC {packet.crc:04X}"
        return "\n".join([head, *_fmt_records(packet.records), f"reply  {packet.ack().hex().upper()}"])
    if isinstance(packet, CommandPacket):
        lines = [f"TCP | Codec {packet.codec_name} | {packet.type_name}"]
        if packet.imei:
            lines.append(f"IMEI  {packet.imei}")
        if packet.timestamp:
            lines.append(f"time  {_fmt_time(packet.timestamp)}")
        lines.append(f"text  {packet.text}")
        return "\n".join(lines)
    raise TypeError(f"not a decoded packet: {type(packet).__name__}")
