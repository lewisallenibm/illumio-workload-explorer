from app.config import settings
from app.ui.illumio_workloads_widget import IllumioWorkloadsWidget


def test_sync_button_explicitly_identifies_mock_or_read_only_pce_mode(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_USE_REAL_CLIENT", False)
    assert IllumioWorkloadsWidget._sync_button_label() == "Sync Mock Illumio"

    monkeypatch.setattr(settings, "ILLUMIO_USE_REAL_CLIENT", True)
    assert IllumioWorkloadsWidget._sync_button_label() == "Sync Illumio PCE (Read Only)"
    assert "never writes" in IllumioWorkloadsWidget._sync_button_tooltip().casefold()
