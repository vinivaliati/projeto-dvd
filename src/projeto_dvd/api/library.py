"""Library pages: disc folders, one folder's files, and the scan."""

import threading
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from projeto_dvd.api.deps import FolderDep, MediaDirDep, SessionDep, templates
from projeto_dvd.api.dvd import dvd_state
from projeto_dvd.jobs import store
from projeto_dvd.library.files import list_disc_folders
from projeto_dvd.library.probe import FfprobeMissingError, run_ffprobe
from projeto_dvd.library.scan import folder_view, purge_missing_folders, scan_folder

router = APIRouter()

# One scan at a time (per process; the app runs a single uvicorn worker): ffprobe is heavy
# on a USB drive, and two scans of the same folder would race on the same rows.
_scan_lock = threading.Lock()
# The folder being scanned: halfway through, its rows look like "changed" files.
_scanning: str | None = None

SCAN_RUNNING = "Já existe um scan em andamento. Aguarde ele terminar."
FFPROBE_MISSING = (
    "O ffprobe não foi encontrado, então nada foi lido. Confira as ferramentas em /health."
)


@router.get("/", response_class=HTMLResponse, name="library")
def library_page(request: Request, session: SessionDep, media_dir: MediaDirDep) -> HTMLResponse:
    folders = list_disc_folders(media_dir)
    purge_missing_folders(session, folders)
    views = [folder_view(session, media_dir, name, path) for name, path in folders.items()]
    context = {"folders": views, "scanning": _scanning, "active": store.active_folders(session)}
    return templates.TemplateResponse(request, "library.html", context)


@router.get("/folders/{name}", response_class=HTMLResponse, name="folder")
def folder_page(
    request: Request, name: str, folder: FolderDep, session: SessionDep, media_dir: MediaDirDep
) -> HTMLResponse:
    view = folder_view(session, media_dir, name, folder)
    # The body template is shared with the scan response: no scan result on a plain GET.
    context = {
        "folder": view,
        "scan_error": None,
        "probed": None,
        "scanning": _scanning,
        "dvd": dvd_state(session, view),
        "now": datetime.now(UTC),
    }
    return templates.TemplateResponse(request, "folder.html", context)


@router.post("/folders/{name}/scan", response_class=HTMLResponse, name="scan_folder")
def scan(
    request: Request, name: str, folder: FolderDep, session: SessionDep, media_dir: MediaDirDep
) -> HTMLResponse:
    """Scan synchronously (sync route: runs in the thread pool) and return the folder body."""
    global _scanning
    error = None
    probed = None
    if not _scan_lock.acquire(blocking=False):
        error = SCAN_RUNNING
    else:
        try:
            _scanning = name
            probed = scan_folder(session, media_dir, name, folder, run_ffprobe)
        except FfprobeMissingError:
            error = FFPROBE_MISSING
        finally:
            _scanning = None
            _scan_lock.release()
    view = folder_view(session, media_dir, name, folder)
    # Our own scan has finished here; a refused one shows the scan that is still running.
    context = {
        "folder": view,
        "scan_error": error,
        "probed": probed,
        "scanning": _scanning,
        "dvd": dvd_state(session, view),
        "now": datetime.now(UTC),
    }
    return templates.TemplateResponse(request, "_folder_body.html", context)
