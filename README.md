# teltonika-decoder

A small Python decoder for packets from Teltonika GPS trackers (FMB, FMC, FMM, FMP and similar). It uses only the standard library: one file does the parsing, and a CLI sits on top.

| Supported | |
|---|---|
| IMEI handshake | ✅ |
| Codec 8 / Codec 8 Extended (8E) / Codec 16 over TCP | ✅ CRC-16 checked |
| Same codecs over UDP | ✅ |
| GPRS commands: Codec 12, 13, 14 | ✅ decode + encode |
| Server replies (IMEI accept, TCP record ack, UDP ack) | ✅ |

## Install

```bash
pip install git+https://github.com/ryanc2112/teltonika-decoder
```

Or copy `src/teltonika/` into your project. It has no dependencies. Requires Python 3.9 or newer.

## Command line

```console
$ teltonika-decode 000000000000002808010000016B40D9AD80010000000000000000000000000000000103021503010101425E100000010000F22A
TCP | Codec 8 | 1 record(s) | CRC F22A
#1  2019-06-10 10:05:36 UTC  priority 1
    GPS  0.0000000, 0.0000000  alt 0 m  angle 0 deg  sats 0  speed 0 km/h  (no fix)
    event IO 1  |  3 IO element(s)
       21  GSM Signal             3
        1  Digital Input 1        1
       66  External Voltage       24080
reply  00000001
```

- `--json` prints machine-readable output.
- Pipe in a file of hex frames to decode them in bulk (one frame per line): `teltonika-decode --json < frames.txt`
- `--no-crc` decodes a frame even when its CRC is wrong.
- `--command getinfo` encodes a Codec 12 command. Add `--imei 3520...` to encode it as Codec 14 instead.
- `python -m teltonika` works the same way once the package is installed (from a clone: `pip install -e .`).

## Library

```python
import teltonika

packet = teltonika.decode(raw_bytes_or_hex)   # works out TCP / UDP / IMEI by itself

for rec in packet.records:
    print(rec.timestamp, rec.gps.latitude, rec.gps.longitude, rec.gps.speed)
    ignition = rec.io.get(239)                # IO values are unsigned ints; Codec 8E NX values are bytes

reply = packet.ack()                          # send this back so the device drops the records
```

| Function | Returns |
|---|---|
| `decode(data, verify_crc=True)` | IMEI `str`, `AVLPacket`, `UDPPacket` or `CommandPacket` |
| `decode_tcp`, `decode_udp`, `decode_imei` | the same, when you already know the transport |
| `encode_command(text, imei=None)` | the bytes of a Codec 12 command, or Codec 14 when you pass `imei` |
| `to_dict(packet)` / `format_packet(packet)` | JSON-ready dict / readable text |
| `crc16_ibm(data)` | the CRC-16/IBM that TCP frames use |

Bad input raises `TeltonikaError`, or `CRCError` (a subclass of it) when only the CRC is wrong.

## Example server

`examples/server.py` is a small asyncio TCP server. It accepts the handshake, decodes each packet, prints it and acks it:

```bash
python examples/server.py --port 5027
```

Point a device's server settings at this machine's IP and port, using TCP. The server is for bench testing only: it has no authentication, no IMEI allowlist and no storage.

## Notes

- Coordinates are in decimal degrees and timestamps are in UTC.
- `GPS.valid` is `False` when the device reports 0 satellites. That means there was no fix, and lat/lon are then 0 or the last known position.
- IO values are raw integers. What they mean depends on the IO ID and on the device model. Some IDs are signed or scaled, for example voltages in mV. `IO_NAMES` labels only the common IDs; for the rest, check the AVL ID list for your device on the Teltonika wiki.
- This project follows Teltonika's public protocol documentation. The tests use the sample packets published there.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
