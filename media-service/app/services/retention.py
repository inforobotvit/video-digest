"""Delete sources and sweep old artifacts.

Working artifacts (audio.*, subs.*, chunks/, source.*, raw/) expire RETENTION_HOURS after the
source was last touched; playback.mp3 expires PLAYBACK_RETENTION_DAYS after it was written.
"""

import logging
import shutil
import time
from pathlib import Path

from app.config import Settings
from app.models import DeleteResponse, SweepResponse
from app.services import storage
from app.services.download import PLAYBACK_NAME

log = logging.getLogger(__name__)

KEEP_ALWAYS = frozenset({storage.META_NAME})


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def delete_source(settings: Settings, source_id: str, keep_playback: bool) -> DeleteResponse:
    src_dir = storage.source_dir(settings, source_id)
    if not src_dir.is_dir():
        return DeleteResponse(deleted=False, source_id=source_id)

    playback = src_dir / PLAYBACK_NAME
    if not keep_playback or not playback.is_file():
        shutil.rmtree(src_dir, ignore_errors=True)
        log.info("source deleted", extra={"source_id": source_id, "kept": []})
        return DeleteResponse(deleted=True, source_id=source_id)

    for entry in src_dir.iterdir():
        if entry.name in KEEP_ALWAYS or entry.name == PLAYBACK_NAME:
            continue
        _remove(entry)
    meta = storage.read_meta(settings, source_id)
    if meta is not None:
        storage.record_operation(
            settings, meta, "delete", params={"keep": "playback"}, result={"kept": [PLAYBACK_NAME]}
        )
    log.info("source deleted", extra={"source_id": source_id, "kept": [PLAYBACK_NAME]})
    return DeleteResponse(deleted=True, source_id=source_id, kept=[PLAYBACK_NAME])


def _last_activity(src_dir: Path) -> float:
    """Newest mtime among everything except playback.mp3 (which has its own clock)."""
    newest = src_dir.stat().st_mtime
    for path in src_dir.rglob("*"):
        if path.name == PLAYBACK_NAME:
            continue
        try:
            newest = max(newest, path.stat().st_mtime)
        except FileNotFoundError:
            continue
    return newest


def sweep(settings: Settings, now: float | None = None) -> SweepResponse:
    now = time.time() if now is None else now
    work_cutoff = now - settings.retention_hours * 3600
    playback_cutoff = now - settings.playback_retention_days * 86400
    report = SweepResponse()
    if not settings.data_dir.is_dir():
        return report

    for src_dir in sorted(settings.data_dir.iterdir()):
        if not src_dir.is_dir():
            continue
        if src_dir.name == storage.tmp_dir(settings).name:
            for leftover in src_dir.iterdir():
                if leftover.stat().st_mtime < work_cutoff:
                    _remove(leftover)
                    report.removed.append(str(leftover))
            continue

        report.checked += 1
        playback = src_dir / PLAYBACK_NAME
        # Decide before deleting: removing children bumps the directory mtime.
        stale = _last_activity(src_dir) < work_cutoff
        if stale:
            for entry in src_dir.iterdir():
                if entry.name in KEEP_ALWAYS or entry.name == PLAYBACK_NAME:
                    continue
                _remove(entry)
                report.removed.append(str(entry))
        if playback.is_file() and playback.stat().st_mtime < playback_cutoff:
            _remove(playback)
            report.removed.append(str(playback))

        remaining = [p for p in src_dir.iterdir() if p.name not in KEEP_ALWAYS]
        if not remaining and stale:
            shutil.rmtree(src_dir, ignore_errors=True)
            report.sources_removed.append(src_dir.name)

    if report.removed or report.sources_removed:
        log.info(
            "retention sweep",
            extra={
                "checked": report.checked,
                "removed": len(report.removed),
                "sources_removed": report.sources_removed,
            },
        )
    return report
