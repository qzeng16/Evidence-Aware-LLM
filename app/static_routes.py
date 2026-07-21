"""Same-origin routes for browser Demo assets."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter()

STATIC_DIRECTORY = (
    Path(__file__).resolve().parent
    / "static"
)


@router.get(
    "/assets/demo.css",
    include_in_schema=False,
)
def demo_stylesheet() -> FileResponse:
    """Return the browser Demo stylesheet."""

    return FileResponse(
        STATIC_DIRECTORY / "demo.css",
        media_type="text/css",
    )


@router.get(
    "/assets/demo.js",
    include_in_schema=False,
)
def demo_javascript() -> FileResponse:
    """Return the browser Demo JavaScript."""

    return FileResponse(
        STATIC_DIRECTORY / "demo.js",
        media_type="application/javascript",
    )
