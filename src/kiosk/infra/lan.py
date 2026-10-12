"""This hub's address on the restaurant network, told to the cloud with every heartbeat so screens
always find it, even when LAN_URL isn't set or the router gives the hub a new IP address."""

import os
import socket

from kiosk.config import settings


def local_ip() -> str | None:
    """The IP of the network card that reaches the internet (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip: str = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


def lan_url() -> str | None:
    if settings.lan_url:
        return settings.lan_url.rstrip("/")
    ip = local_ip()
    return f"http://{ip}:{os.environ.get('KIOSK_PORT', '8000')}" if ip else None
