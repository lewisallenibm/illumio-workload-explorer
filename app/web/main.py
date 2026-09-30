"""Local web pilot entry point: ``python -m app.web.main``.

The browser UI is a presentation layer over the same PostgreSQL repositories
and services used by the desktop application.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from app.database import SessionLocal
from app.config import settings
from app.models.cmdb_ci import CmdbCi
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.reconciliation_run import ReconciliationRun
from app.repositories.cmdb_repository import CmdbRepository, ReconciliationRepository
from app.repositories.illumio_workload_repository import IllumioWorkloadRepository
from app.services.automation_service import AutomationConfigurationError, AutomationService
from app.services.cmdb_import_service import CmdbImportService
from app.services.illumio.illumio_sync_service import IllumioSyncService
from app.services.illumio.pce_preflight_service import PcePreflightService
from app.services.illumio.workloader_source_adapter import WorkloaderCsvSourceAdapter
from app.services.illumio_write_back_service import IllumioWriteBackService
from app.services.mock_cmdb_sync_service import MockCmdbSyncService
from app.services.reconciliation_service import ReconciliationService
from app.services.web_operation_service import WebOperationService
from app.web.access_auth import (
    AccessConfigurationError,
    AccessTokenError,
    validate_public_access_configuration,
    verify_cloudflare_access_token,
)

WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent.parent
UPLOAD_ROOT = PROJECT_ROOT / "var" / "web-upload-previews"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 200
PAGE_SIZES = (100, 250, 500, 1000)
templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))
automation_service = AutomationService()
operation_service = WebOperationService()

# ---------------------------------------------------------------------------
# Structured JSON logger — all state-changing events are written here so
# that IBM SIEM / log aggregation can index them without screen-scraping HTML.
# ---------------------------------------------------------------------------
_audit_log = logging.getLogger("illumio.web.audit")
if not _audit_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_log.addHandler(_handler)
    _audit_log.setLevel(logging.INFO)


def _audit(action: str, request: Request, **extra) -> None:
    """Emit one structured audit-log line per state-changing request."""
    email = getattr(getattr(request, "state", None), "access_email", None) or "local"
    _audit_log.info(json.dumps({
        "event": action,
        "actor": email,
        "path": str(request.url.path),
        "method": request.method,
        **{k: str(v) for k, v in extra.items()},
    }, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Pilot user allowlist (H-1).
# In public mode, WEB_PILOT_ALLOWED_EMAILS is a comma-separated list of the
# exact Cloudflare Access email addresses that may use the application.
# An empty / missing value permits all authenticated users (safe for a strictly
# controlled local-only deployment; must be set for any shared public pilot).
# ---------------------------------------------------------------------------
def _allowed_emails() -> frozenset[str]:
    raw = os.getenv("WEB_PILOT_ALLOWED_EMAILS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(addr.strip().casefold() for addr in raw.split(",") if addr.strip())


def _check_pilot_access(request: Request) -> bool:
    """Return True if the request is permitted under the current allowlist."""
    allowed = _allowed_emails()
    if not allowed:
        return True  # allowlist not configured — permit all authenticated users
    email = getattr(getattr(request, "state", None), "access_email", None) or ""
    return email.casefold() in allowed


# ---------------------------------------------------------------------------
# In-memory sliding-window rate limiter & cooldown guard (M-5).
# Bounded state table protecting state-changing actions and file uploads.
# ---------------------------------------------------------------------------
_RATE_LIMITS: dict[str, list[float]] = {}
_RATE_LOCK = time.monotonic


def _is_rate_limited(key: str, max_requests: int = 10, window_seconds: float = 60.0) -> bool:
    """Sliding-window request count check per actor/IP."""
    now = time.monotonic()
    timestamps = _RATE_LIMITS.setdefault(key, [])
    # Evict timestamps outside the window
    _RATE_LIMITS[key] = [t for t in timestamps if now - t < window_seconds]
    if len(_RATE_LIMITS[key]) >= max_requests:
        return True
    _RATE_LIMITS[key].append(now)
    return False


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.WEB_DEPLOYMENT_MODE == "public":
        validate_public_access_configuration()
    elif settings.WEB_DEPLOYMENT_MODE != "local":
        raise AccessConfigurationError("WEB_DEPLOYMENT_MODE must be local or public.")
    automation_service.bootstrap_defaults()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Illumio Workload Explorer Web Pilot", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)


class DeploymentAccessMiddleware(BaseHTTPMiddleware):
    """Local loopback in development; verified Cloudflare Access in public mode."""

    _LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

    @staticmethod
    def _secure(response, *, public: bool = False):
        """Apply browser protections to HTML, API, and static responses."""
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; script-src 'self'; style-src 'self'")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        if public:
            # L-6: Strict-Transport-Security for HTTPS-only public deployments.
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    @staticmethod
    def _same_origin(request: Request) -> bool:
        """Require browsers in public mode to submit state changes to this host."""
        origin = request.headers.get("origin", "")
        parsed = urlparse(origin)
        host = request.headers.get("host", "").casefold()
        return parsed.scheme == "https" and bool(parsed.netloc) and parsed.netloc.casefold() == host

    async def dispatch(self, request: Request, call_next):
        if settings.WEB_DEPLOYMENT_MODE == "local":
            if (request.client.host if request.client else "") not in self._LOOPBACK_HOSTS:
                return self._secure(PlainTextResponse("This unauthenticated web pilot accepts localhost requests only.", status_code=403))
            return self._secure(await call_next(request))

        # A load balancer needs an unauthenticated liveness response. It
        # reveals no application data and every user-facing path is guarded.
        if request.url.path == "/health":
            return self._secure(await call_next(request), public=True)
        try:
            claims = verify_cloudflare_access_token(
                request.headers.get("cf-access-jwt-assertion", "")
            )
            request.state.access_email = claims.get("email")
        except (AccessConfigurationError, AccessTokenError):
            return self._secure(PlainTextResponse("Cloudflare Access authentication is required.", status_code=403), public=True)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not self._same_origin(request):
            return self._secure(PlainTextResponse("Cross-site state-changing requests are not allowed.", status_code=403), public=True)
        # H-1: pilot user allowlist check — applied after authentication so
        # the email claim is available.
        if not _check_pilot_access(request):
            return self._secure(PlainTextResponse("Your account is not on the pilot access list.", status_code=403), public=True)
        # M-5: In-app rate limiting on mutating requests (max 30 actions/min per user/IP)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            actor_key = getattr(request.state, "access_email", None) or (request.client.host if request.client else "unknown")
            if _is_rate_limited(f"mutate:{actor_key}", max_requests=30, window_seconds=60.0):
                return self._secure(PlainTextResponse("Too many requests. Please wait a moment before trying again.", status_code=429), public=True)
        return self._secure(await call_next(request), public=True)


app.add_middleware(DeploymentAccessMiddleware)
app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")


def _dashboard_context() -> dict:
    with SessionLocal() as session:
        latest_run = session.query(ReconciliationRun).filter(ReconciliationRun.status == "SUCCESS").order_by(ReconciliationRun.completed_at.desc(), ReconciliationRun.id.desc()).first()
        return {"workload_count": session.query(func.count(IllumioWorkload.id)).scalar() or 0, "cmdb_count": session.query(func.count(CmdbCi.id)).scalar() or 0, "latest_run": latest_run}


def _pagination(total: int, page: int, page_size: int) -> dict:
    page_size = page_size if page_size in PAGE_SIZES else 100
    page_count = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, page_count))
    return {"page": page, "page_count": page_count, "page_size": page_size, "offset": (page - 1) * page_size, "showing_from": 0 if total == 0 else (page - 1) * page_size + 1, "showing_to": min(page * page_size, total)}


def _query_url(request: Request, **changes: object) -> str:
    params = dict(request.query_params)
    for key, value in changes.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = str(value)
    return f"{request.url.path}?{urlencode(params)}" if params else request.url.path


templates.env.globals["query_url"] = _query_url


def _render(request: Request, page: str, **context):
    context.setdefault("dashboard", _dashboard_context())
    context.update(request=request, page=page, page_sizes=PAGE_SIZES, external_delivery_enabled=os.getenv("AUTOMATION_ENABLE_EXTERNAL_DELIVERY", "false").casefold() == "true")
    return templates.TemplateResponse(request=request, name="base.html", context=context)


def _redirect(path: str, message: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {key: value for key, value in {"message": message, "error": error}.items() if value}
    if params:
        path = f"{path}{'&' if '?' in path else '?'}{urlencode(params)}"
    return RedirectResponse(path, status_code=303)


def _time_from_picker(hour: str | None, minute: str | None, *, allow_inherit: bool = False) -> str | None:
    """Build an HH:MM UTC value from the constrained web form selectors."""
    hour = (hour or "").strip()
    minute = (minute or "").strip()
    if not hour and not minute and allow_inherit:
        return None
    if not hour or not minute:
        raise AutomationConfigurationError("Choose both an hour and a minute.")
    try:
        hour_number, minute_number = int(hour), int(minute)
    except ValueError as exc:
        raise AutomationConfigurationError("Choose a valid hour and minute.") from exc
    if hour_number not in range(24) or minute_number not in range(60):
        raise AutomationConfigurationError("Choose a valid hour and minute.")
    return f"{hour_number:02d}:{minute_number:02d}"


def _weekday_from_picker(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        weekday = int(value)
    except ValueError as exc:
        raise AutomationConfigurationError("Choose a valid weekday.") from exc
    if weekday not in range(7):
        raise AutomationConfigurationError("Choose a valid weekday.")
    return weekday


async def _save_upload(upload: UploadFile, allowed_suffixes: set[str]) -> Path:
    filename = Path(upload.filename or "upload").name
    suffix = Path(filename).suffix.casefold()
    if suffix not in allowed_suffixes:
        raise HTTPException(400, f"Unsupported file type. Expected: {', '.join(sorted(allowed_suffixes))}.")
    destination = UPLOAD_ROOT / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Upload is larger than the 500 MB pilot limit.")
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    _validate_upload_content(destination, suffix)
    return destination


def _validate_upload_content(path: Path, suffix: str) -> None:
    """Reject renamed binary files and dangerous XLSX archive expansion early."""
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
        first_bytes = sample[:8]
        if suffix == ".csv":
            if b"\0" in sample:
                raise ValueError("CSV files cannot contain binary null bytes.")
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                handle.read(4096)
        elif suffix == ".xlsx":
            if not first_bytes.startswith(b"PK\x03\x04"):
                raise ValueError("XLSX files must be valid Office Open XML archives.")
            with zipfile.ZipFile(path) as archive:
                files = archive.infolist()
                uncompressed = sum(item.file_size for item in files)
                compressed = sum(item.compress_size for item in files)
                if uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ValueError("XLSX expands beyond the 1 GB safety limit.")
                if compressed and uncompressed / compressed > MAX_XLSX_COMPRESSION_RATIO:
                    raise ValueError("XLSX compression ratio exceeds the safety limit.")
        elif suffix == ".xls" and first_bytes != bytes.fromhex("D0CF11E0A1B11AE1"):
            raise ValueError("XLS files must use the legacy Office binary signature.")
    except (OSError, UnicodeError, zipfile.BadZipFile, ValueError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Uploaded file failed safety validation: {exc}") from exc


def _upload_path(token: str, allowed_suffixes: set[str]) -> Path:
    if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
        raise HTTPException(400, "Upload preview token is invalid.")
    matches = [path for path in UPLOAD_ROOT.glob(f"{token}.*") if path.suffix.casefold() in allowed_suffixes]
    if len(matches) != 1:
        raise HTTPException(404, "The upload preview has expired. Select the file again.")
    return matches[0]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _render(request, "home")


@app.get("/workloads", response_class=HTMLResponse)
def workloads(request: Request, q: str = "", online: str = "All", enforcement: str = "All", page: int = 1, page_size: int = 100, sort_by: str = "hostname", sort_direction: str = "asc", operation_id: str | None = None, message: str | None = None, error: str | None = None):
    started = time.perf_counter()
    online_value = {"Online": True, "Offline": False}.get(online)
    enforcement_value = None if enforcement == "All" else enforcement
    total = IllumioWorkloadRepository.count(q or None, online_value, enforcement_value)
    pagination = _pagination(total, page, page_size)
    rows = IllumioWorkloadRepository.search(q or None, online_value, enforcement_value, limit=pagination["page_size"], offset=pagination["offset"], sort_by=sort_by, sort_direction=sort_direction)
    return _render(request, "workloads", rows=rows, total=total, pagination=pagination, filters={"q": q, "online": online, "enforcement": enforcement, "sort_by": sort_by, "sort_direction": sort_direction}, metadata=IllumioWorkloadRepository.latest_ingestion_metadata(), elapsed_ms=round((time.perf_counter() - started) * 1000, 1), operation=operation_service.get(operation_id) if operation_id else None, message=message, error=error)


@app.get("/workloads/{workload_id}", response_class=HTMLResponse)
def workload_detail(request: Request, workload_id: int):
    workload = IllumioWorkloadRepository.get_by_id(workload_id)
    if workload is None:
        raise HTTPException(404, "Workload was not found.")
    return _render(request, "workload_detail", workload=workload)


@app.get("/workloads/{workload_id}/panel", response_class=HTMLResponse)
def workload_detail_panel(request: Request, workload_id: int):
    """Return the workload detail card as an HTML fragment for the inline drawer."""
    workload = IllumioWorkloadRepository.get_by_id(workload_id)
    if workload is None:
        raise HTTPException(404, "Workload was not found.")
    return _render(request, "workload_detail_panel", workload=workload)


@app.get("/workloads/by-hostname/{hostname}/panel", response_class=HTMLResponse)
def workload_panel_by_hostname(request: Request, hostname: str):
    """Return the workload detail card by hostname — used by reconciliation inline drawer."""
    workload = IllumioWorkloadRepository.get_by_hostname(hostname)
    if workload is None:
        raise HTTPException(404, "Workload was not found.")
    return _render(request, "workload_detail_panel", workload=workload)


@app.post("/workloads/sync")
def sync_workloads(request: Request):
    _audit("workloads.sync", request)
    operation = operation_service.start(
        "Illumio workload sync",
        lambda progress: (progress(0, 0, "Reading and ingesting workloads"), IllumioSyncService.sync()),
    )
    return _redirect(f"/workloads?operation_id={operation.id}", "Workload sync started in the background.")


@app.post("/workloads/pce-preflight")
def workload_pce_preflight(request: Request):
    _audit("workloads.pce_preflight", request)
    try:
        result = PcePreflightService.check()
        return _redirect("/workloads", result.get("message") or f"PCE preflight: {result.get('status', 'completed')}")
    except Exception as exc:
        _audit_log.error(json.dumps({"event": "workloads.pce_preflight.error", "detail": repr(exc)}))
        return _redirect("/workloads", error="PCE preflight failed. Check server logs for details.")


@app.post("/workloads/import/preview", response_class=HTMLResponse)
async def preview_workloader_import(request: Request, upload: UploadFile = File(...)):
    path = await _save_upload(upload, {".csv"})
    preview = WorkloaderCsvSourceAdapter.preview(path)
    if not preview.valid:
        path.unlink(missing_ok=True)
        return _render(request, "workload_import_preview", preview=preview, upload_token=None)
    return _render(request, "workload_import_preview", preview=preview, upload_token=path.stem)


@app.post("/workloads/import/confirm")
def confirm_workloader_import(request: Request, token: str = Form(...)):
    path = _upload_path(token, {".csv"})
    _audit("workloads.import.confirm", request)
    try:
        preview, records = WorkloaderCsvSourceAdapter.load_records(path)
        result = IllumioSyncService.sync(records=records)
        return _redirect("/workloads", f"Workloader CSV imported safely: {preview.readable_rows} read; {getattr(result, 'inserted', 0)} inserted; {getattr(result, 'updated', 0)} updated.")
    except Exception as exc:
        _audit_log.error(json.dumps({"event": "workloads.import.confirm.error", "detail": repr(exc)}))
        return _redirect("/workloads", error="Workloader import did not change the current dataset. Check server logs for details.")
    finally:
        path.unlink(missing_ok=True)


@app.post("/workloads/bulk", response_class=HTMLResponse)
def workload_bulk_search(request: Request, terms: str = Form(""), online: str = Form("All"), enforcement: str = Form("All")):
    clean = [line.strip() for line in terms.splitlines() if line.strip()]
    if len(clean) > 10_000:
        return _render(request, "bulk_results", title="Workload bulk search", error="Bulk search accepts up to 10,000 nonblank lines.", found=[], missing=[])
    result = IllumioWorkloadRepository.bulk_search(clean, {"Online": True, "Offline": False}.get(online), None if enforcement == "All" else enforcement)
    return _render(request, "bulk_results", title="Workload bulk search", found=result["found"], missing=result["missing"], entity="workload")


@app.get("/cmdb", response_class=HTMLResponse)
def cmdb(request: Request, q: str = "", app_filter: str = "", region: str = "", page: int = 1, page_size: int = 100, sort_by: str = "hostname", sort_direction: str = "asc", operation_id: str | None = None, message: str | None = None, error: str | None = None):
    started = time.perf_counter()
    total = CmdbRepository.count(q or None, app_filter or None, region or None)
    pagination = _pagination(total, page, page_size)
    rows = CmdbRepository.search(q or None, app_filter or None, region or None, limit=pagination["page_size"], offset=pagination["offset"], sort_by=sort_by, sort_direction=sort_direction)
    return _render(request, "cmdb", rows=rows, total=total, pagination=pagination, filters={"q": q, "app_filter": app_filter, "region": region, "sort_by": sort_by, "sort_direction": sort_direction}, metadata=CmdbRepository.latest_import_metadata(), elapsed_ms=round((time.perf_counter() - started) * 1000, 1), operation=operation_service.get(operation_id) if operation_id else None, message=message, error=error)


@app.get("/cmdb/{hostname}/panel", response_class=HTMLResponse)
def cmdb_detail_panel(request: Request, hostname: str):
    """Return a CMDB record as an HTML fragment for the inline drawer."""
    record = CmdbRepository.get_by_hostname(hostname)
    if record is None:
        raise HTTPException(404, "CMDB record was not found.")
    return _render(request, "cmdb_detail_panel", record=record)


@app.post("/cmdb/mock")
def load_mock_cmdb(request: Request):
    _audit("cmdb.mock_load", request)
    def load(progress):
        progress(0, 300_000, "Generating and staging mock CMDB rows")
        MockCmdbSyncService.sync(
            count=300_000,
            progress_callback=lambda current, total: progress(current, total, "Staging mock CMDB rows"),
        )

    operation = operation_service.start("Load 300k Mock CMDB", load)
    return _redirect(f"/cmdb?operation_id={operation.id}", "Mock CMDB load started in the background.")


@app.post("/cmdb/import/preview", response_class=HTMLResponse)
async def preview_cmdb_import(request: Request, upload: UploadFile = File(...)):
    path = await _save_upload(upload, {".csv", ".xlsx", ".xls"})
    preview = CmdbImportService.preview(path)
    if not preview.valid:
        path.unlink(missing_ok=True)
        return _render(request, "cmdb_import_preview", preview=preview, upload_token=None)
    return _render(request, "cmdb_import_preview", preview=preview, upload_token=path.stem)


@app.post("/cmdb/import/confirm")
def confirm_cmdb_import(request: Request, token: str = Form(...)):
    path = _upload_path(token, {".csv", ".xlsx", ".xls"})
    _audit("cmdb.import.confirm", request)
    try:
        result = CmdbImportService.import_file(path)
        inserted = result.get("inserted", result.get("records_imported", "unknown"))
        _audit("cmdb.import.success", request, inserted=inserted)
        return _redirect("/cmdb", f"CMDB snapshot activated safely: {inserted} records imported.")
    except Exception as exc:
        _audit_log.error(json.dumps({"event": "cmdb.import.error", "detail": repr(exc)}))
        return _redirect("/cmdb", error="CMDB import did not replace the active snapshot. Check server logs for details.")
    finally:
        path.unlink(missing_ok=True)


@app.post("/cmdb/bulk", response_class=HTMLResponse)
def cmdb_bulk_search(request: Request, terms: str = Form(""), app_filter: str = Form(""), region: str = Form("")):
    clean = [line.strip() for line in terms.splitlines() if line.strip()]
    if len(clean) > 10_000:
        return _render(request, "bulk_results", title="CMDB bulk search", error="Bulk search accepts up to 10,000 nonblank lines.", found=[], missing=[])
    result = CmdbRepository.bulk_search(clean, app_filter or None, region or None)
    return _render(request, "bulk_results", title="CMDB bulk search", found=result["found"], missing=result["missing"], entity="cmdb")


@app.get("/reconciliation", response_class=HTMLResponse)
def reconciliation(request: Request, run_id: int | None = None, hostname: str = "", status: str = "All", field: str = "All", action: str = "All", page: int = 1, page_size: int = 100, sort_by: str = "hostname", sort_direction: str = "asc", operation_id: str | None = None, message: str | None = None, error: str | None = None):
    started = time.perf_counter()
    selected_run = run_id or ReconciliationRepository.latest_run_id()
    total = ReconciliationRepository.count(status, field, action, hostname or None, selected_run or None)
    pagination = _pagination(total, page, page_size)
    rows = ReconciliationRepository.search(status, field, action, hostname or None, selected_run or None, limit=pagination["page_size"], offset=pagination["offset"], sort_by=sort_by, sort_direction=sort_direction)
    context = ReconciliationRepository.get_run_context(selected_run) if selected_run else None
    with SessionLocal() as session:
        runs = session.query(ReconciliationRun).order_by(ReconciliationRun.id.desc()).limit(30).all()
    return _render(request, "reconciliation", rows=rows, runs=runs, selected_run=selected_run, run_context=context, total=total, pagination=pagination, filters={"hostname": hostname, "status": status, "field": field, "action": action, "sort_by": sort_by, "sort_direction": sort_direction}, elapsed_ms=round((time.perf_counter() - started) * 1000, 1), operation=operation_service.get(operation_id) if operation_id else None, message=message, error=error)


@app.post("/reconciliation/run")
def run_reconciliation(request: Request):
    _audit("reconciliation.run", request)
    operation = operation_service.start(
        "Run reconciliation",
        lambda progress: (progress(0, 0, "Comparing saved CMDB and Illumio snapshots"), ReconciliationService.run()),
    )
    return _redirect(f"/reconciliation?operation_id={operation.id}", "Reconciliation started in the background.")


@app.get("/operations/{operation_id}")
def operation_status(operation_id: str):
    operation = operation_service.get(operation_id)
    if operation is None:
        raise HTTPException(404, "Operation was not found or has expired.")
    return JSONResponse(operation)


@app.post("/reconciliation/approve")
def approve_results(request: Request, result_ids: list[int] = Form([]), run_id: int | None = Form(None)):
    if not result_ids:
        return _redirect("/reconciliation", error="Select at least one reconciliation result first.")
    ReconciliationRepository.mark_approved(result_ids)
    _audit("reconciliation.approve", request, count=len(result_ids), run_id=run_id)
    return _redirect(f"/reconciliation?run_id={run_id or ''}", f"Approved {len(result_ids)} selected result(s).")


@app.post("/reconciliation/skip")
def skip_results(request: Request, result_ids: list[int] = Form([]), run_id: int | None = Form(None)):
    if not result_ids:
        return _redirect("/reconciliation", error="Select at least one reconciliation result first.")
    ReconciliationRepository.mark_skipped(result_ids)
    _audit("reconciliation.skip", request, count=len(result_ids), run_id=run_id)
    return _redirect(f"/reconciliation?run_id={run_id or ''}", f"Skipped {len(result_ids)} selected result(s).")


@app.post("/reconciliation/preview")
def preview_approved(request: Request, run_id: int | None = Form(None)):
    _audit("reconciliation.preview_approved", request, run_id=run_id)
    summary = IllumioWriteBackService.preview_approved(run_id)
    return _redirect(f"/reconciliation?run_id={run_id or ''}", "Approved-change preflight: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


@app.post("/reconciliation/apply")
def apply_approved(request: Request, run_id: int | None = Form(None), confirm_live_write: bool = Form(False)):
    if not confirm_live_write:
        return _redirect("/reconciliation", error="Live PCE write-back requires the explicit confirmation checkbox and the existing PCE environment guards.")
    _audit("reconciliation.apply", request, run_id=run_id, confirmed=True)
    result = IllumioWriteBackService.apply_approved(run_id)
    _audit("reconciliation.apply.result", request, **result)
    return _redirect(f"/reconciliation?run_id={run_id or ''}", "PCE write-back result: " + ", ".join(f"{key}={value}" for key, value in result.items()))


@app.get("/automations", response_class=HTMLResponse)
def automations(request: Request, message: str | None = None, error: str | None = None):
    return _render(request, "automations", automations=automation_service.list_automations(), recipients=automation_service.list_recipients(), subscriptions=automation_service.list_subscriptions(), runs=automation_service.recent_runs(), message=message, error=error)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, message: str | None = None, error: str | None = None):
    """Browser-local presentation preferences plus read-only PCE diagnostics."""
    return _render(
        request,
        "settings",
        message=message,
        error=error,
        pce_read_mode_enabled=settings.ILLUMIO_USE_REAL_CLIENT,
        pce_host=settings.ILLUMIO_PCE_HOST or "Not configured",
        pce_org_id=settings.ILLUMIO_ORG_ID,
    )


@app.post("/settings/pce-test")
def settings_pce_test(request: Request):
    _audit("settings.pce_test", request)
    try:
        result = PcePreflightService.check()
        if result.get("status") == "CONNECTED":
            count = result.get("workload_count")
            suffix = f" Workload count: {count}." if count is not None else ""
            return _redirect("/settings", f"PCE connection succeeded (read-only).{suffix}")
        return _redirect("/settings", result.get("message") or "PCE connection test did not run.")
    except Exception as exc:
        _audit_log.error(json.dumps({"event": "settings.pce_test.error", "detail": repr(exc)}))
        return _redirect("/settings", error="PCE connection test failed. Check server logs for details.")


@app.post("/automations/{automation_id}")
def save_automation(request: Request, automation_id: int, enabled: bool = Form(False), schedule_type: str = Form(...), weekday: str | None = Form(None), run_hour: str = Form(...), run_minute: str = Form(...), delivery_channels: list[str] = Form([]), box_folder_id: str | None = Form(None)):
    try:
        run_time_utc = _time_from_picker(run_hour, run_minute)
        weekday_number = _weekday_from_picker(weekday)
        automation_service.update_automation(automation_id, enabled=enabled, schedule_type=schedule_type, weekday=weekday_number, run_time_utc=run_time_utc, delivery_channels=delivery_channels, box_folder_id=box_folder_id)
        _audit("automations.save", request, automation_id=automation_id)
        return _redirect("/automations", "Automation saved")
    except AutomationConfigurationError as exc:
        return _redirect("/automations", error=str(exc))


@app.post("/automations/{automation_id}/run")
def run_automation(request: Request, automation_id: int):
    _audit("automations.run_now", request, automation_id=automation_id)
    run = automation_service.run_now(automation_id)
    return _redirect("/automations", "Pilot artifact created in local outbox" if run.status == "SUCCESS" else None, run.error_message if run.status != "SUCCESS" else None)


@app.post("/recipients/{slot}")
def save_recipient(request: Request, slot: int, display_name: str = Form(...), email: str = Form(...), enabled: bool = Form(False)):
    try:
        automation_service.save_recipient(slot=slot, display_name=display_name, email=email, enabled=enabled)
        _audit("recipients.save", request, slot=slot)
        return _redirect("/automations", "Recipient saved")
    except AutomationConfigurationError as exc:
        return _redirect("/automations", error=str(exc))


@app.post("/recipients/{slot}/delete")
def delete_recipient(request: Request, slot: int):
    try:
        automation_service.delete_recipient(slot=slot)
        _audit("recipients.delete", request, slot=slot)
        return _redirect("/automations", "Recipient deleted")
    except AutomationConfigurationError as exc:
        return _redirect("/automations", error=str(exc))


@app.post("/subscriptions/{automation_id}/{recipient_id}")
def save_subscription(request: Request, automation_id: int, recipient_id: int, enabled: bool = Form(False), schedule_type: str = Form("INHERIT"), weekday: str | None = Form(None), run_hour: str | None = Form(None), run_minute: str | None = Form(None)):
    try:
        run_time_utc = _time_from_picker(run_hour, run_minute, allow_inherit=True)
        weekday_number = _weekday_from_picker(weekday)
        automation_service.set_subscription(automation_id=automation_id, recipient_id=recipient_id, enabled=enabled, schedule_type=schedule_type, weekday=weekday_number, run_time_utc=run_time_utc)
        _audit("subscriptions.save", request, automation_id=automation_id, recipient_id=recipient_id)
        return _redirect("/automations", "Recipient delivery setting saved")
    except AutomationConfigurationError as exc:
        return _redirect("/automations", error=str(exc))


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    host = "127.0.0.1" if settings.WEB_DEPLOYMENT_MODE == "local" else "0.0.0.0"  # nosec B104
    uvicorn.run("app.web.main:app", host=host, port=int(os.getenv("PORT", "8000")), reload=False)
