"""Menu photos: owners upload an image; screens show it from /media/<venue>/<file>.

The upload body is the raw image (Content-Type image/jpeg, image/png or image/webp), max 5 MB.
In the cloud, MEDIA_DIR should be backed by object storage (e.g. an S3 bucket mounted or synced).
"""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from ulid import ULID

from kiosk.api.deps import Admin, AdminVenue
from kiosk.config import settings
from kiosk.errors import AppError

router = APIRouter(prefix="/v1/admin/venues/{venue_id}", tags=["admin: menu"])

MAX_BYTES = 5 * 1024 * 1024
TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG"),
    "image/webp": ("webp", b"RIFF"),
}


@router.post("/media", status_code=201)
async def upload(
    request: Request, venue: AdminVenue, admin: Admin, content_type: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind not in TYPES:
        raise AppError("bad_image", "Upload a JPEG, PNG or WebP image")
    body = await request.body()
    if not body or len(body) > MAX_BYTES:
        raise AppError("bad_image", "The image must be between 1 byte and 5 MB")
    ext, magic = TYPES[kind]
    if not body.startswith(magic) or (ext == "webp" and body[8:12] != b"WEBP"):
        raise AppError("bad_image", "The file is not a valid image of that type")
    folder = Path(settings.media_dir) / venue.id
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{ULID()}.{ext}"
    (folder / name).write_bytes(body)
    return {"url": f"/media/{venue.id}/{name}", "bytes": len(body)}
