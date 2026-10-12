"""ESC/POS slips and the printers that can be reached straight from the server.

Printers in the venue are normally reached through the cloud print queue (services/printing):
cloud printers fetch their jobs, screen-attached printers get them from their screen.

Thermal printers can't render Sinhala or Tamil from text commands, so printed slips use
English names. Printing Sinhala/Tamil needs raster images; that can be added later.
"""

import asyncio
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from ulid import ULID

ESC, GS = b"\x1b", b"\x1d"
WIDTH = 42  # characters on 80 mm paper, font A


class Slip(bytes):
    """ESC/POS bytes, plus the same slip as plain text for printers that are sent text."""

    text: str

    def __new__(cls, data: bytes, text: str) -> "Slip":
        slip = super().__new__(cls, data)
        slip.text = text
        return slip


class EscPos:
    def __init__(self) -> None:
        self.buf = bytearray(ESC + b"@")  # initialise
        self.lines: list[str] = []

    def text(self, value: str = "") -> "EscPos":
        # Printers take plain ASCII here: "Café" prints as "Cafe", anything else as "?".
        folded = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
        plain = folded.encode("ascii", "replace")
        self.buf += plain + b"\n"
        self.lines.append(plain.decode())
        return self

    def align(self, where: str) -> "EscPos":
        self.buf += ESC + b"a" + bytes([{"left": 0, "center": 1, "right": 2}[where]])
        return self

    def bold(self, on: bool = True) -> "EscPos":
        self.buf += ESC + b"E" + bytes([1 if on else 0])
        return self

    def size(self, w: int = 1, h: int = 1) -> "EscPos":
        self.buf += GS + b"!" + bytes([((w - 1) << 4) | (h - 1)])
        return self

    def row(self, left: str, right: str) -> "EscPos":
        space = max(1, WIDTH - len(left) - len(right))
        return self.text(f"{left[: WIDTH - len(right) - 1]}{' ' * space}{right}")

    def rule(self) -> "EscPos":
        return self.text("-" * WIDTH)

    def feed(self, lines: int = 3) -> "EscPos":
        self.buf += ESC + b"d" + bytes([lines])
        return self

    def cut(self) -> "EscPos":
        self.buf += GS + b"V" + b"\x42\x00"
        return self

    def barcode(self, data: str) -> "EscPos":
        """CODE128 barcode with the text printed under it (GS k, function B)."""
        payload = b"{B" + data.encode("ascii")
        self.buf += GS + b"h" + bytes([80]) + GS + b"w" + bytes([2]) + GS + b"H" + bytes([2])
        self.buf += GS + b"k" + bytes([73, len(payload)]) + payload + b"\n"
        self.lines.append(f"*{data}*")
        return self

    def kick_drawer(self) -> "EscPos":
        self.buf += ESC + b"p" + b"\x00\x19\xfa"
        return self

    def bytes(self) -> Slip:
        return Slip(bytes(self.buf), "\n".join(self.lines) + "\n")


class Printer(Protocol):
    async def send(self, data: bytes, label: str) -> None: ...


class NetworkPrinter:
    """Raw TCP (port 9100), supported by almost every Ethernet receipt printer."""

    def __init__(self, host: str, port: int = 9100, timeout: float = 4.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    async def send(self, data: bytes, label: str) -> None:
        _, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)
        writer.write(data)
        await asyncio.wait_for(writer.drain(), self.timeout)
        writer.close()
        await writer.wait_closed()


class FilePrinter:
    """Dev/test printer: writes each job to a .bin file."""

    def __init__(self, directory: str) -> None:
        self.dir = Path(directory)

    async def send(self, data: bytes, label: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{ULID()}-{label}.bin").write_bytes(data)


class NullPrinter:
    async def send(self, data: bytes, label: str) -> None:
        return None


def build_printer(config: dict[str, Any], print_dir: str) -> Printer:
    kind = config.get("type", "file")
    if kind == "network":
        return NetworkPrinter(config["host"], int(config.get("port", 9100)))
    if kind == "none":
        return NullPrinter()
    return FilePrinter(print_dir)
