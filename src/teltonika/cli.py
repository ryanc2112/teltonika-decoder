"""Command line: teltonika-decode <hex>  (or pipe hex frames in, one per line)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .decoder import TeltonikaError, decode, encode_command
from .output import format_packet, to_dict


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="teltonika-decode",
        description="Decode Teltonika packets (Codec 8, 8E, 16, 12, 13, 14; TCP, UDP, IMEI handshake).",
    )
    parser.add_argument("hex", nargs="*", help="hex frame(s); spaces allowed. Reads stdin, one per line, if omitted")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--no-crc", action="store_true", help="decode TCP frames even when the CRC is wrong")
    parser.add_argument("--command", metavar="TEXT", help="encode a Codec 12 GPRS command and print its hex")
    parser.add_argument("--imei", help="with --command: build a Codec 14 command for this IMEI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.command is not None:
        print(encode_command(args.command, imei=args.imei).hex().upper())
        return 0

    frames = [" ".join(args.hex)] if args.hex else [ln for ln in sys.stdin.read().splitlines() if ln.strip()]
    if not frames:
        parser.error("no hex given")

    failed = 0
    results = []
    for frame in frames:
        try:
            packet = decode(frame, verify_crc=not args.no_crc)
        except TeltonikaError as exc:
            failed += 1
            if args.json:
                results.append({"error": str(exc), "input": frame.strip()})
            else:
                print(f"error: {exc}", file=sys.stderr)
            continue
        if args.json:
            results.append(to_dict(packet))
        else:
            if len(frames) > 1 and results:
                print()
            print(format_packet(packet))
            results.append(None)

    if args.json:
        print(json.dumps(results[0] if len(results) == 1 else results, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
