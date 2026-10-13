"""Service configuration, read from environment (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path("/data")
    upload_max_mb: int = Field(default=500, gt=0)
    retention_hours: int = Field(default=48, gt=0)
    playback_retention_days: int = Field(default=30, gt=0)
    retention_sweep_minutes: int = Field(default=30, ge=0, description="0 disables the loop")

    ytdlp_cookies_file: Path | None = None
    ytdlp_proxy: str | None = None

    audio_format: Literal["wav", "mp3"] = "wav"
    audio_mp3_bitrate: str = "64k"
    playback_bitrate: str = "96k"

    chunk_sec_default: int = Field(default=600, gt=0)
    chunk_max_mb_default: float = Field(default=24, gt=0)
    chunk_bitrate: str = "64k"
    # Silence search around each chunk boundary (see /split in the TZ).
    split_window_sec: float = Field(default=20, ge=0)
    silence_noise_db: float = -30
    silence_min_sec: float = Field(default=0.3, gt=0)

    # Empty string disables the check (dev only).
    api_key: str = ""

    log_level: str = "INFO"

    # Subprocess timeouts (seconds).
    probe_timeout_sec: float = Field(default=90, gt=0)
    ffprobe_timeout_sec: float = Field(default=30, gt=0)
    download_timeout_sec: float = Field(default=1800, gt=0)
    # How long a second request on the same source_id waits for the first one (download, split)
    # before answering 409 source_busy. A 90-minute video on the VPS takes 3-5 minutes end to end
    # (yt-dlp, work track, playback, split); 600 is about twice that and well below the 30-minute
    # HTTP timeout of the orchestrator, so the refusal arrives as a JSON error, never as a dropped
    # connection.
    source_lock_wait_sec: float = Field(default=600, gt=0)
    # Direct-file links: the redirect-checking HEAD request before ffprobe reads the file over HTTP.
    direct_head_timeout_sec: float = Field(default=15, gt=0)

    # Binary names or absolute paths; overridable for tests and local runs.
    ytdlp_bin: str = "yt-dlp"
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    @field_validator("ytdlp_cookies_file", "ytdlp_proxy", mode="before")
    @classmethod
    def _empty_env_is_none(cls, value: object) -> object:
        # `.env` files commonly carry `KEY=` for unset options; treat that as None.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
