"""Minimal asyncio TCP server for Teltonika devices.

Accepts the IMEI handshake, decodes every AVL packet, prints it, and sends the
ack so the device deletes the records from its memory.

    python examples/server.py --port 5027

Point the device's server settings at this machine (protocol TCP).
Not for production: no authentication, no persistence, no IMEI allowlist.
"""

import argparse
import asyncio
import json

import teltonika as t


async def read_frame(reader: asyncio.StreamReader) -> bytes:
    """Read one TCP AVL/command frame: preamble + length + body + CRC."""
    header = await reader.readexactly(8)
    length = int.from_bytes(header[4:8], "big")
    if length > 1_000_000:
        raise t.TeltonikaError(f"frame length {length} is implausible")
    return header + await reader.readexactly(length + 4)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, as_json: bool) -> None:
    peer = writer.get_extra_info("peername")
    try:
        size = int.from_bytes(await reader.readexactly(2), "big")
        imei = t.decode_imei((size).to_bytes(2, "big") + await reader.readexactly(size))
        print(f"[{peer[0]}] connected, IMEI {imei}")
        writer.write(t.encode_imei_ack())
        await writer.drain()

        while True:
            packet = t.decode_tcp(await read_frame(reader))
            print(json.dumps(t.to_dict(packet)) if as_json else t.format_packet(packet))
            if isinstance(packet, t.AVLPacket):
                writer.write(packet.ack())
                await writer.drain()
    except asyncio.IncompleteReadError:
        print(f"[{peer[0]}] disconnected")
    except t.TeltonikaError as exc:
        print(f"[{peer[0]}] bad frame, closing: {exc}")
    finally:
        writer.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5027)
    parser.add_argument("--json", action="store_true", help="print one JSON object per packet")
    args = parser.parse_args()

    server = await asyncio.start_server(lambda r, w: handle(r, w, args.json), args.host, args.port)
    print(f"listening on {args.host}:{args.port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
