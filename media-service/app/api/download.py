"""POST /download."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models import DownloadRequest, DownloadResponse, ErrorResponse
from app.services import download

router = APIRouter(tags=["download"])

_ERRORS = {
    404: {"model": ErrorResponse, "description": "source_not_found / subtitles_not_found"},
    410: {"model": ErrorResponse, "description": "source_not_found (upload already removed)"},
    500: {"model": ErrorResponse, "description": "ffmpeg_failed"},
    502: {"model": ErrorResponse, "description": "ytdlp_failed / subtitles_format"},
    504: {"model": ErrorResponse, "description": "download_timeout / ytdlp_timeout"},
}


@router.post("/download", response_model=DownloadResponse, responses=_ERRORS)
def download_artifact(
    body: DownloadRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> DownloadResponse:
    # Sync endpoint on purpose: yt-dlp/ffmpeg block for minutes, FastAPI moves it to a thread.
    return download.download(body, settings)
