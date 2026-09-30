from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.web import main as web
from app.web.access_auth import AccessConfigurationError, validate_public_access_configuration
from app.config import settings


def _request(path):
    return Request({"type": "http", "method": "GET", "path": path, "query_string": b"", "headers": [], "client": ("testclient", 1234)})


def _dashboard():
    return {"workload_count": 0, "cmdb_count": 0, "latest_run": None}


def test_workload_screen_renders_database_controls(monkeypatch):
    row = SimpleNamespace(id=1, hostname="server01", name=None, online=True, enforcement_mode="full", ven_version="24.1", os="ubuntu")
    monkeypatch.setattr(web, "_dashboard_context", _dashboard)
    monkeypatch.setattr(web.IllumioWorkloadRepository, "count", staticmethod(lambda *args: 1))
    monkeypatch.setattr(web.IllumioWorkloadRepository, "search", staticmethod(lambda *args, **kwargs: [row]))
    monkeypatch.setattr(web.IllumioWorkloadRepository, "latest_ingestion_metadata", staticmethod(lambda: None))

    response = web.workloads(_request("/workloads"))
    body = response.body.decode()
    assert "Sync Mock Illumio" in body
    assert "Preview Import" in body
    assert "Bulk Search" in body
    assert "Page 1 of 1" in body
    assert "server01" in body
    assert 'value="100" selected' in body


def test_cmdb_screen_renders_import_search_and_fast_paging(monkeypatch):
    row = SimpleNamespace(hostname="ci-1", cmdb_app="app", cmdb_role="role", cmdb_env="prod", cmdb_loc="loc", region="east", ven_installed="Yes")
    monkeypatch.setattr(web, "_dashboard_context", _dashboard)
    monkeypatch.setattr(web.CmdbRepository, "count", staticmethod(lambda *args: 1))
    monkeypatch.setattr(web.CmdbRepository, "search", staticmethod(lambda *args, **kwargs: [row]))
    monkeypatch.setattr(web.CmdbRepository, "latest_import_metadata", staticmethod(lambda: None))

    response = web.cmdb(_request("/cmdb"))
    body = response.body.decode()
    assert "Load 300k Mock CMDB" in body
    assert "Preview Import" in body
    assert "Bulk Search" in body
    assert "Page 1 of 1" in body
    assert "ci-1" in body
    assert 'value="100" selected' in body


def test_redirect_preserves_existing_query_string():
    assert web._redirect("/reconciliation?run_id=3", "saved").headers["location"] == "/reconciliation?run_id=3&message=saved"


def test_constrained_schedule_pickers_build_valid_values():
    assert web._time_from_picker("07", "05") == "07:05"
    assert web._time_from_picker("", "", allow_inherit=True) is None
    assert web._weekday_from_picker("0") == 0
    assert web._weekday_from_picker("") is None

    with pytest.raises(web.AutomationConfigurationError):
        web._time_from_picker("24", "00")


def test_public_mode_requires_cloudflare_access_configuration(monkeypatch):
    monkeypatch.setattr(settings, "WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN", "")
    monkeypatch.setattr(settings, "WEB_CLOUDFLARE_ACCESS_AUD", "")
    with pytest.raises(AccessConfigurationError):
        validate_public_access_configuration()

    monkeypatch.setattr(settings, "WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN", "https://team.cloudflareaccess.com")
    monkeypatch.setattr(settings, "WEB_CLOUDFLARE_ACCESS_AUD", "audience-tag")
    validate_public_access_configuration()


def test_settings_screen_has_apply_based_appearance_choice(monkeypatch):
    monkeypatch.setattr(web, "_dashboard_context", _dashboard)
    response = web.settings_page(_request("/settings"))
    body = response.body.decode()
    assert "Apply appearance" in body
    assert "Dark" in body
    assert "Light" in body
    assert "Test PCE Connection (Read Only)" in body
    assert "Credentials are never shown" in body
    assert "Open Working Guide" in body
    assert "Illumio and CMDB Working Guide" in body
    assert "documentation_viewer.js" in body


def test_settings_pce_test_reports_a_read_only_success(monkeypatch):
    monkeypatch.setattr(web.PcePreflightService, "check", staticmethod(lambda: {"status": "CONNECTED", "workload_count": 42}))

    req = Request(scope={"type": "http", "method": "POST", "path": "/settings/pce-test", "headers": []})
    response = web.settings_pce_test(req)

    assert response.headers["location"] == "/settings?message=PCE+connection+succeeded+%28read-only%29.+Workload+count%3A+42."


def test_reconciliation_screen_renders_actions_and_result_filters(monkeypatch):
    row = SimpleNamespace(id=7, hostname="server01", field_name="role", illumio_value="old", cmdb_value="new", status="LABEL_MISMATCH", resolution_action="pending")

    class Query:
        def order_by(self, *args):
            return self

        def limit(self, *args):
            return self

        def all(self):
            return []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def query(self, *args):
            return Query()

    monkeypatch.setattr(web, "_dashboard_context", _dashboard)
    monkeypatch.setattr(web, "SessionLocal", lambda: Session())
    monkeypatch.setattr(web.ReconciliationRepository, "latest_run_id", staticmethod(lambda: 1))
    monkeypatch.setattr(web.ReconciliationRepository, "count", staticmethod(lambda *args: 1))
    monkeypatch.setattr(web.ReconciliationRepository, "search", staticmethod(lambda *args, **kwargs: [row]))
    monkeypatch.setattr(web.ReconciliationRepository, "get_run_context", staticmethod(lambda *args: None))

    response = web.reconciliation(_request("/reconciliation"))
    body = response.body.decode()
    assert "Run Reconciliation" in body
    assert "Approve Selected" in body
    assert "Preview Approved Changes" in body
    assert "Page 1 of 1" in body
    assert "server01" in body
    assert 'value="100" selected' in body
