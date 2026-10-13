"""Store an uploaded file as a source: /data/{source_id}/source.{ext}."""

import hashlib
import logging
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from app.config import Settings
from app.errors import ApiError
from app.models import ProbeResponse, SourceMeta
from app.services import ffprobe, storage
from app.services.source_id import SOURCE_ID_LEN

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({"mp4", "mov", "mkv", "webm", "mp3", "m4a", "wav", "ogg", "flac"})
SOURCE_PREFIX = "source"


def extension_of(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ApiError("unsupported_file", f"extension '{ext or '?'}' not in: {allowed}", 400)
    return ext


def check_declared_size(content_length: int | None, settings: Settings) -> None:
    limit = settings.upload_max_mb * 1024 * 1024
    if content_length is not None and content_length > limit:
        raise ApiError(
            "file_too_large", f"file exceeds UPLOAD_MAX_MB={settings.upload_max_mb}", 413
        )


async def save_upload(
    chunks: AsyncIterator[bytes], filename: str, settings: Settings
) -> ProbeResponse:
    ext = extension_of(filename)
    limit = settings.upload_max_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0

    tmp_path = storage.tmp_dir(settings) / f"upload-{os.getpid()}-{id(chunks)}.{ext}"
    try:
        with tmp_path.open("wb") as out:
            async for chunk in chunks:
                size += len(chunk)
                if size > limit:
                    raise ApiError(
                        "file_too_large",
                        f"file exceeds UPLOAD_MAX_MB={settings.upload_max_mb}",
                        413,
                    )
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise ApiError("invalid_media", "empty file", 400)

        source_id = digest.hexdigest()[:SOURCE_ID_LEN]
        target_dir = storage.source_dir(settings, source_id)
        target = target_dir / f"{SOURCE_PREFIX}.{ext}"
        existing = storage.read_meta(settings, source_id)
        if existing is not None and target.is_file():
            log.info("upload deduplicated", extra={"source_id": source_id})
            storage.record_operation(
                settings, existing, "upload", params={"filename": filename, "size": size}
            )
            return existing.probe

        info = ffprobe.probe_file(tmp_path, settings)
        # ffprobe opens plain text via its tty/lrc demuxers: no audio or video streams at all.
        if not info.has_audio and not info.has_video:
            raise ApiError("invalid_media", "file is not a readable audio/video container", 400)
        if not info.has_audio:
            raise ApiError("no_audio", "file has no audio stream", 400)

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)

    probe = ProbeResponse(
        source_id=source_id,
        platform="upload",
        title=Path(filename).stem or source_id,
        duration_sec=info.duration_sec,
        recommended="transcribe",
    )
    meta = SourceMeta(
        source_id=source_id,
        kind="upload",
        original_filename=Path(filename).name,
        created_at=storage.now(),
        probe=probe,
    )
    storage.record_operation(
        settings,
        meta,
        "upload",
        params={"filename": filename, "size": size},
        result={"path": str(target), "format": info.format_name, "has_video": info.has_video},
    )
    log.info(
        "upload done",
        extra={"source_id": source_id, "size": size, "duration_sec": info.duration_sec},
    )
    return probe
