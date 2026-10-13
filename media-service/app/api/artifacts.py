"""GET /artifacts/{source_id}/{name}, GET|DELETE /sources/{source_id}, POST /maintenance/sweep."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import FileResponse

from app.auth import require_api_key
from app.config import Settings, get_settings
from app.errors import ApiError
from app.models import (
    DeleteResponse,
    ErrorResponse,
    SourceId,
    SourceInfo,
    SweepResponse,
    ToolVersions,
)
from app.services import artifacts, retention, storage

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]
SourceIdPath = Annotated[SourceId, Path()]


@router.get(
    "/artifacts/{source_id}/{name:path}",
    tags=["artifacts"],
    response_class=FileResponse,
    responses={404: {"model": ErrorResponse}, 206: {"description": "partial content (Range)"}},
)
def get_artifact(source_id: SourceIdPath, name: str, settings: SettingsDep) -> FileResponse:
    # FileResponse handles Range / If-Range and sets Accept-Ranges: bytes.
    path = artifacts.resolve(settings, source_id, name)
    return FileResponse(path, media_type=artifacts.media_type(path), filename=path.name)


@router.get(
    "/sources/{source_id}",
    tags=["sources"],
    response_model=SourceInfo,
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_source(source_id: SourceIdPath, settings: SettingsDep, request: Request) -> SourceInfo:
    """Probe result and origin of a source, for the orchestrator (needs the API key)."""
    meta = storage.read_meta(settings, source_id)
    if meta is None:
        raise ApiError("source_not_found", f"unknown source_id {source_id}", 404)
    versions = getattr(request.app.state, "binaries", None)
    tools = (
        ToolVersions(
            ytdlp=versions.ytdlp,
            ejs=versions.ejs,
            js_runtime=versions.js_runtime,
            ffmpeg=versions.ffmpeg,
        )
        if versions
        else None
    )
    return SourceInfo(
        source_id=meta.source_id,
        kind=meta.kind,
        url=meta.url,
        original_filename=meta.original_filename,
        probe=meta.probe,
        tools=tools,
    )


@router.delete("/sources/{source_id}", tags=["sources"], response_model=DeleteResponse)
def delete_source(
    source_id: SourceIdPath,
    settings: SettingsDep,
    keep: Annotated[Literal["playback"] | None, Query()] = None,
) -> DeleteResponse:
    return retention.delete_source(settings, source_id, keep_playback=keep == "playback")


@router.post("/maintenance/sweep", tags=["maintenance"], response_model=SweepResponse)
def run_sweep(settings: SettingsDep) -> SweepResponse:
    """Run the retention sweep now (the same one the background loop runs)."""
    return retention.sweep(settings)
