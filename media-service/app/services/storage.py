"""On-disk state: /data/{source_id}/meta.json plus artifacts."""

import fcntl
import json
import logging
import os
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.errors import ApiError
from app.models import Operation, SourceMeta

log = logging.getLogger(__name__)

META_NAME = "meta.json"


def source_dir(settings: Settings, source_id: str) -> Path:
    return settings.data_dir / source_id


def tmp_dir(settings: Settings) -> Path:
    path = settings.data_dir / ".tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def source_lock(settings: Settings, source_id: str) -> Iterator[None]:
    """Serialize the artifact-producing work of one source (download, split).

    Two jobs on the same source_id at once are normal (the same link from a post, the same file
    uploaded twice): without the lock both requests transcoded into one temp file, the first rename
    stole it from the second (FileNotFoundError, 500) and for links the second rmtree wiped the
    first's yt-dlp download. With the lock the second request waits and then takes the artifact the
    first produced through the existing "already there" early returns. flock works across threads
    (separate open() calls) and across worker processes; the lock files live under .tmp/locks so
    they never show up as artifacts and retention ignores them.

    The wait is bounded (SOURCE_LOCK_WAIT_SEC): a producer stuck for longer must not keep the source
    hostage while the waiter hangs on an open connection until the orchestrator's timeout, an error
    nobody can read. Past the bound the waiter gets 409 source_busy with a plain message.
    """
    locks = tmp_dir(settings) / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + settings.source_lock_wait_sec
    with (locks / f"{source_id}.lock").open("a+") as fh:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    log.warning(
                        "source busy",
                        extra={"source_id": source_id, "waited_sec": settings.source_lock_wait_sec},
                    )
                    raise ApiError(
                        "source_busy",
                        f"source {source_id} is being processed by another request for more than "
                        f"{int(settings.source_lock_wait_sec)} s; try again later",
                        409,
                    ) from None
                time.sleep(0.5)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def read_meta(settings: Settings, source_id: str) -> SourceMeta | None:
    path = source_dir(settings, source_id) / META_NAME
    if not path.is_file():
        return None
    try:
        return SourceMeta.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        log.warning("corrupt meta.json, ignoring", extra={"source_id": source_id})
        return None


def write_meta(settings: Settings, meta: SourceMeta) -> Path:
    """Atomic write: temp file in the same dir, then rename."""
    directory = source_dir(settings, meta.source_id)
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / META_NAME
    tmp = directory / f".{META_NAME}.tmp"
    tmp.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, final)
    return final


def record_operation(
    settings: Settings,
    meta: SourceMeta,
    op: str,
    params: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
) -> SourceMeta:
    meta.operations.append(
        Operation(op=op, at=now(), params=params or {}, result=result or {})  # type: ignore[arg-type]
    )
    write_meta(settings, meta)
    return meta


def remove_source(settings: Settings, source_id: str) -> bool:
    directory = source_dir(settings, source_id)
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True


def now() -> datetime:
    return datetime.now(tz=UTC)


def dump_json(path: Path, payload: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
