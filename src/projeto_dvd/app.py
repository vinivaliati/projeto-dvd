"""Web application: hello page and health check."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from projeto_dvd.tools import detect_versions

app = FastAPI(title="projeto-dvd")
templates = Jinja2Templates(directory=Path(__file__).parent / "web" / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
def health() -> JSONResponse:
    """Report media tool versions; 503 if any tool is missing (the image is broken)."""
    tools = detect_versions()
    ok = all(tools.values())
    return JSONResponse(
        {"status": "ok" if ok else "missing", "tools": tools},
        status_code=200 if ok else 503,
    )
