"""SMS gateways (Sri Lanka: e.g. Notify.lk, Text.lk, Dialog / Mobitel bulk SMS).

One interface: send(phone, text, sender) -> provider message id, raising SmsError. Only the mock
exists; a provider's adapter implements the same method with its API key. The mock writes every
message to sms.log next to the print files, so tests and demos can read what a guest would get.
"""

import json
from pathlib import Path
from typing import Protocol

from ulid import ULID

from kiosk.config import settings


class SmsError(Exception):
    pass


class SmsSender(Protocol):
    async def send(self, phone: str, text: str, sender: str) -> str: ...


class MockSms:
    def __init__(self, directory: str) -> None:
        self.file = Path(directory) / "sms.log"

    async def send(self, phone: str, text: str, sender: str) -> str:
        if phone.endswith("0000000"):  # lets tests see a failure
            raise SmsError("Number not reachable")
        ref = f"MOCKSMS-{ULID()}"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with self.file.open("a") as f:
            f.write(json.dumps({"ref": ref, "to": phone, "from": sender, "text": text}) + "\n")
        return ref


def get_sms() -> SmsSender:
    return MockSms(settings.print_dir)
