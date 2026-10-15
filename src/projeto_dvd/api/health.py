"""Health check: media tool versions."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from projeto_dvd.tools import detect_versions

router = APIRouter()


@router.get("/health", name="health")
def health() -> JSONResponse:
    """Report media tool versions; 503 if any tool is missing (the image is broken)."""
    tools = detect_versions()
    ok = all(tools.values())
    return JSONResponse(
        {"status": "ok" if ok else "missing", "tools": tools},
        status_code=200 if ok else 503,
    )
