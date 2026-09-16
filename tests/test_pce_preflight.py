from types import SimpleNamespace

from app.config import settings
from app.services.illumio.pce_preflight_service import PcePreflightService
from app.services.illumio.real_illumio_client import RealIllumioClient


def test_preflight_is_disabled_without_explicit_real_client_mode(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_USE_REAL_CLIENT", False)
    result = PcePreflightService.check()
    assert result["status"] == "DISABLED"
    assert "ILLUMIO_USE_REAL_CLIENT=true" in result["message"]


def test_real_client_preflight_uses_one_read_only_workload_request(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_PCE_HOST", "pce.example.test")
    monkeypatch.setattr(settings, "ILLUMIO_API_KEY_ID", "id")
    monkeypatch.setattr(settings, "ILLUMIO_API_KEY_SECRET", "secret")
    client = RealIllumioClient()
    captured = {}
    client._get = lambda path, params: captured.update(path=path, params=params) or SimpleNamespace(
        headers={"X-Total-Count": "42"}
    )
    assert client.preflight() == {"status": "CONNECTED", "workload_count": 42}
    assert captured == {
        "path": "/workloads",
        "params": {"max_results": 1, "offset": 0, "representation": "workload_labels"},
    }
