"""Turn yt-dlp metadata into a ProbeResponse and persist meta.json."""

import logging
import re
from typing import Any

from app.config import Settings
from app.errors import ApiError
from app.models import ProbeResponse, SourceMeta, SubtitleLanguages
from app.services import ffprobe, safe_url, storage, ytdlp
from app.services.source_id import source_id_for_media

log = logging.getLogger(__name__)

# YouTube lists live chat replay under "subtitles"; it is not a caption track.
_NOT_A_CAPTION = frozenset({"live_chat"})
_LANG_RE = re.compile(r"^[a-z]{2,3}")


def _language_from_key(key: str) -> str:
    """'en-US' -> 'en', 'ru-orig' -> 'ru'."""
    match = _LANG_RE.match(key.lower())
    return match.group(0) if match else key


def subtitle_languages(info: dict[str, Any]) -> SubtitleLanguages:
    manual = sorted(
        {_language_from_key(k) for k in info.get("subtitles") or {} if k not in _NOT_A_CAPTION}
    )
    auto_raw = info.get("automatic_captions") or {}
    # yt-dlp marks the spoken-language track as "<lang>-orig"; the rest are auto-translations.
    orig = [k for k in auto_raw if k.endswith("-orig")]
    if orig:
        auto_keys = orig
    elif info.get("language") in auto_raw:
        auto_keys = [info["language"]]
    else:
        auto_keys = list(auto_raw)
    auto = sorted({_language_from_key(k) for k in auto_keys if k not in _NOT_A_CAPTION})
    return SubtitleLanguages(manual=manual, auto=auto)


def recommend(subs: SubtitleLanguages) -> str:
    # Auto captions are deliberately not recommended: quality is too low for a digest.
    return "subtitles_manual" if subs.manual else "transcribe"


def guess_language(info: dict[str, Any], subs: SubtitleLanguages) -> str | None:
    """Rule 1.1 of docs/result-schema.md: manual subtitles define the language of the video.

    Metadata is not trusted over them: a TED-Ed re-upload said "en" while its only manual track was
    "ru", and the pipeline can only read a manual track. Among several manual tracks the metadata
    language wins, then the spoken-language ("<lang>-orig") auto track, then the first one.
    """
    lang = _language_from_key(info["language"]) if info.get("language") else None
    if subs.manual:
        if lang in subs.manual:
            return lang
        for auto in subs.auto:
            if auto in subs.manual:
                return auto
        return subs.manual[0]
    if lang:
        return lang
    if len(subs.auto) == 1:
        return subs.auto[0]
    return None


def build_probe_response(info: dict[str, Any]) -> ProbeResponse:
    if info.get("_type") not in (None, "video"):
        raise ApiError("unsupported_url", "playlists and channels are not supported", 400)
    extractor = str(info.get("extractor") or "").lower()
    media_id = str(info.get("id") or "")
    if not extractor or not media_id:
        raise ApiError("ytdlp_failed", "metadata has no extractor/id", 502)
    subs = subtitle_languages(info)
    duration = info.get("duration")
    return ProbeResponse(
        source_id=source_id_for_media(extractor, media_id),
        platform=extractor,
        title=str(info.get("title") or media_id),
        duration_sec=float(duration) if duration is not None else None,
        subtitles=subs,
        recommended=recommend(subs),
        language=guess_language(info, subs),
        thumbnail_url=info.get("thumbnail"),
    )


def probe_url(url: str, settings: Settings) -> ProbeResponse:
    # Every user-supplied address is checked before anything on this server opens it (SSRF guard).
    safe_url.check_public_url(url)
    info = ytdlp.dump_info(url, settings)
    probe = build_probe_response(info)
    download_url: str | None = None
    if probe.platform == "generic" and probe.duration_sec is None:
        # A direct link to a media file: yt-dlp reports no duration for it, and without a duration
        # the job cannot be accepted (length cap, budget). Follow redirects hop by hop, cap the
        # size, then let ffprobe read the container headers over HTTP (2026-09-17, LibriVox mp3).
        download_url, _size = safe_url.resolve_direct(url, settings)
        media = ffprobe.probe_url(download_url, settings)
        if not media.has_audio:
            raise ApiError("unsupported_url", "file has no audio track", 400)
        probe = probe.model_copy(update={"duration_sec": media.duration_sec})

    meta = storage.read_meta(settings, probe.source_id)
    if meta is None:
        meta = SourceMeta(
            source_id=probe.source_id,
            kind="url",
            url=url,
            created_at=storage.now(),
            probe=probe,
            download_url=download_url,
        )
    else:
        meta.probe = probe  # refresh title/subtitles, keep history
        meta.download_url = download_url
    storage.record_operation(settings, meta, "probe", params={"url": url})
    log.info(
        "probe done",
        extra={
            "source_id": probe.source_id,
            "platform": probe.platform,
            "duration_sec": probe.duration_sec,
            "recommended": probe.recommended,
        },
    )
    return probe
