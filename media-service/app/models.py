"""Request/response models. Wire format is defined in docs/TZ-media-service.md."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

# 12 hex chars: sha256(extractor:id)[:12] for URLs, sha256(file bytes)[:12] for uploads.
SourceId = Annotated[str, Field(pattern=r"^[0-9a-f]{12}$", examples=["a1b2c3d4e5f6"])]

Recommended = Literal["subtitles_manual", "subtitles_auto", "transcribe"]
DownloadMode = Literal["subtitles_manual", "subtitles_auto", "audio"]


# --- errors ---------------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# --- health ---------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ytdlp: str | None = Field(description="yt-dlp version, null if the binary is missing")
    ffmpeg: str | None = Field(description="ffmpeg version, null if the binary is missing")
    ejs: str | None = Field(default=None, description="yt-dlp EJS (JS challenge solver) version")
    js_runtime: str | None = Field(
        default=None, description="JS runtime yt-dlp found, e.g. 'deno 2.9.7'; null when none"
    )


class ToolVersions(BaseModel):
    """What produced the probe: the orchestrator records it in jobs.meta.tools, so a broken
    extractor can be told apart from a broken pipeline on old jobs too (2026-09-21)."""

    ytdlp: str | None = None
    ejs: str | None = None
    js_runtime: str | None = None
    ffmpeg: str | None = None


# --- probe / upload -------------------------------------------------------


class ProbeRequest(BaseModel):
    url: HttpUrl


class SubtitleLanguages(BaseModel):
    manual: list[str] = Field(default_factory=list)
    auto: list[str] = Field(default_factory=list)


class ProbeResponse(BaseModel):
    source_id: SourceId
    platform: str = Field(description="yt-dlp extractor name, or 'upload' for files")
    title: str
    duration_sec: float | None
    subtitles: SubtitleLanguages = Field(default_factory=SubtitleLanguages)
    recommended: Recommended
    language: str | None = Field(default=None, description="ISO 639-1 from metadata, if known")
    thumbnail_url: str | None = None


# --- download -------------------------------------------------------------


class DownloadRequest(BaseModel):
    source_id: SourceId
    mode: DownloadMode
    lang: str | None = Field(default=None, description="required for subtitle modes")

    @model_validator(mode="after")
    def _lang_required_for_subtitles(self) -> "DownloadRequest":
        if self.mode != "audio" and not self.lang:
            raise ValueError("lang is required for subtitle modes")
        return self


class Segment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class SubtitlesArtifact(BaseModel):
    artifact: Literal["subtitles"] = "subtitles"
    path: str
    segments: int = Field(ge=0)


class AudioArtifact(BaseModel):
    artifact: Literal["audio"] = "audio"
    path: str
    duration_sec: float
    size_mb: float
    playback_path: str | None = Field(
        default=None, description="playback.mp3 for uploads; null for URL sources"
    )


DownloadResponse = Annotated[SubtitlesArtifact | AudioArtifact, Field(discriminator="artifact")]


# --- split ----------------------------------------------------------------


class SplitRequest(BaseModel):
    source_id: SourceId
    chunk_sec: int | None = Field(default=None, gt=0, description="default: CHUNK_SEC_DEFAULT")
    max_mb: float | None = Field(default=None, gt=0, description="default: CHUNK_MAX_MB_DEFAULT")


class Chunk(BaseModel):
    index: int = Field(ge=0)
    path: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class SplitResponse(BaseModel):
    chunks: list[Chunk]


# --- delete ---------------------------------------------------------------


class DeleteResponse(BaseModel):
    deleted: bool = Field(description="false if the source did not exist")
    source_id: SourceId
    kept: list[str] = Field(
        default_factory=list, description="files left in place, e.g. playback.mp3"
    )


class SweepResponse(BaseModel):
    removed: list[str] = Field(default_factory=list, description="files and dirs deleted")
    sources_removed: list[SourceId] = Field(default_factory=list)
    checked: int = Field(default=0, ge=0, description="source dirs inspected")


# --- GET /sources/{source_id} ---------------------------------------------


class SourceInfo(BaseModel):
    source_id: SourceId
    kind: Literal["url", "upload"]
    url: str | None = None
    original_filename: str | None = None
    probe: "ProbeResponse"
    tools: ToolVersions | None = Field(
        default=None, description="versions of yt-dlp, EJS, JS runtime, ffmpeg"
    )


# --- meta.json (on-disk state per source) ---------------------------------


class Operation(BaseModel):
    op: Literal["probe", "upload", "download", "split", "delete", "retention"]
    at: datetime
    params: dict[str, object] = Field(default_factory=dict)
    result: dict[str, object] = Field(default_factory=dict)


class SourceMeta(BaseModel):
    source_id: SourceId
    kind: Literal["url", "upload"]
    url: str | None = None
    # Direct file links: the URL after redirects, checked hop by hop; yt-dlp downloads from it.
    download_url: str | None = None
    original_filename: str | None = None
    created_at: datetime
    probe: ProbeResponse
    operations: list[Operation] = Field(default_factory=list)
