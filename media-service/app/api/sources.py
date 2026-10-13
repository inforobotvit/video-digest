"""POST /probe and POST /upload."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.config import Settings, get_settings
from app.models import ErrorResponse, ProbeRequest, ProbeResponse
from app.services import probe, upload

router = APIRouter(tags=["sources"])

_ERRORS = {
    400: {"model": ErrorResponse, "description": "unsupported_url / unsupported_file"},
    403: {"model": ErrorResponse, "description": "bot_check"},
    404: {"model": ErrorResponse, "description": "private_or_removed"},
    413: {"model": ErrorResponse, "description": "file_too_large"},
    502: {"model": ErrorResponse, "description": "ytdlp_failed"},
    504: {"model": ErrorResponse, "description": "ytdlp_timeout"},
}

SettingsDep = Annotated[Settings, Depends(get_settings)]
_UPLOAD_CHUNK = 1 << 20


@router.post("/probe", response_model=ProbeResponse, responses=_ERRORS)
def probe_source(body: ProbeRequest, settings: SettingsDep) -> ProbeResponse:
    # Sync endpoint: FastAPI runs it in a thread, so the blocking yt-dlp call does not
    # stall the event loop.
    return probe.probe_url(str(body.url), settings)


@router.post("/upload", response_model=ProbeResponse, responses=_ERRORS)
async def upload_source(
    request: Request,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="video or audio file")],
) -> ProbeResponse:
    length = request.headers.get("content-length")
    upload.check_declared_size(int(length) if length and length.isdigit() else None, settings)

    async def chunks():  # noqa: ANN202
        while data := await file.read(_UPLOAD_CHUNK):
            yield data

    return await upload.save_upload(chunks(), file.filename or "", settings)
