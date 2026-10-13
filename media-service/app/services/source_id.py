"""Deterministic short ids for sources.

URL sources: sha256("{extractor}:{id}")[:12], so every URL form of the same video
(youtu.be/X, watch?v=X, ...) maps to one id. Uploads: sha256 of file content.
"""

import hashlib
from collections.abc import Iterable
from pathlib import Path

SOURCE_ID_LEN = 12
_CHUNK = 1 << 20


def _short(digest: "hashlib._Hash") -> str:
    return digest.hexdigest()[:SOURCE_ID_LEN]


def source_id_for_media(extractor: str, media_id: str) -> str:
    key = f"{extractor.strip().lower()}:{media_id.strip()}"
    return _short(hashlib.sha256(key.encode("utf-8")))


def source_id_for_bytes(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return _short(digest)


def source_id_for_file(path: Path) -> str:
    def _read() -> Iterable[bytes]:
        with path.open("rb") as fh:
            while block := fh.read(_CHUNK):
                yield block

    return source_id_for_bytes(_read())
