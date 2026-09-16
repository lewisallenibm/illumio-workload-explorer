import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.config import settings
from app.web import main as web


def _request(headers=()):
    return Request({"type": "http", "method": "POST", "path": "/cmdb/import/preview", "query_string": b"", "headers": list(headers), "client": ("testclient", 1234)})


def _dashboard():
    return {"workload_count": 0, "cmdb_count": 0, "latest_run": None}


def test_security_headers_are_present():
    response = web.DeploymentAccessMiddleware._secure(PlainTextResponse("ok"))
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_public_post_requires_same_https_origin():
    same_origin = _request([(b"host", b"pilot.example.test"), (b"origin", b"https://pilot.example.test")])
    cross_origin = _request([(b"host", b"pilot.example.test"), (b"origin", b"https://other.example.test")])
    assert web.DeploymentAccessMiddleware._same_origin(same_origin)
    assert not web.DeploymentAccessMiddleware._same_origin(cross_origin)


def test_upload_rejects_renamed_binary_content(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "UPLOAD_ROOT", tmp_path)
    upload = UploadFile(file=BytesIO(b"binary\0payload"), filename="not-really-a-csv.csv")

    with pytest.raises(HTTPException, match="safety validation"):
        asyncio.run(web._save_upload(upload, {".csv"}))

    assert list(tmp_path.iterdir()) == []


def test_upload_rejects_renamed_xlsx_content(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "UPLOAD_ROOT", tmp_path)
    upload = UploadFile(file=BytesIO(b"not-an-office-file"), filename="not-really-an-xlsx.xlsx")

    with pytest.raises(HTTPException, match="safety validation"):
        asyncio.run(web._save_upload(upload, {".xlsx"}))


def test_settings_template_escapes_server_configuration(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_PCE_HOST", "<script>alert('xss')</script>")
    monkeypatch.setattr(web, "_dashboard_context", _dashboard)
    response = web.settings_page(_request())
    body = response.body.decode()

    assert "&lt;script&gt;" in body
    assert "<script>alert" not in body
