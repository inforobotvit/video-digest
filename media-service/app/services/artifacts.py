"""Which files under /data/{source_id}/ may be served, and safe path resolution."""

import re
from pathlib import Path

from app.config import Settings
from app.errors import ApiError
from app.services import storage

# Served artifacts only: never meta.json, manifest.json, source.* or raw/ downloads.
_SERVABLE = re.compile(
    r"^(subs\.[A-Za-z0-9-]+\.json|audio\.(wav|mp3)|playback\.mp3|chunks/\d{3}\.mp3)$"
)

MEDIA_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".json": "application/json"}


def resolve(settings: Settings, source_id: str, name: str) -> Path:
    if not _SERVABLE.match(name):
        raise ApiError("not_found", f"no such artifact: {name}", 404)
    base = storage.source_dir(settings, source_id).resolve()
    path = (base / name).resolve()
    if base not in path.parents or not path.is_file():
        raise ApiError("not_found", f"no such artifact: {name}", 404)
    return path


def media_type(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
