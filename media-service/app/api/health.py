from fastapi import APIRouter, Request

from app.models import HealthResponse
from app.services.binaries import BinaryVersions

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    versions: BinaryVersions = request.app.state.binaries
    status = "ok" if versions.all_present else "degraded"
    return HealthResponse(
        status=status,
        ytdlp=versions.ytdlp,
        ffmpeg=versions.ffmpeg,
        ejs=versions.ejs,
        js_runtime=versions.js_runtime,
    )
