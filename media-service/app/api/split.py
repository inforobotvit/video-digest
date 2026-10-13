"""POST /split."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models import ErrorResponse, SplitRequest, SplitResponse
from app.services import split

router = APIRouter(tags=["split"])

_ERRORS = {
    404: {"model": ErrorResponse, "description": "source_not_found"},
    409: {"model": ErrorResponse, "description": "audio_not_found (run /download mode=audio)"},
    500: {"model": ErrorResponse, "description": "ffmpeg_failed / chunk_too_large"},
    504: {"model": ErrorResponse, "description": "download_timeout"},
}


@router.post("/split", response_model=SplitResponse, responses=_ERRORS)
def split_audio(
    body: SplitRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> SplitResponse:
    return split.split(body, settings)
