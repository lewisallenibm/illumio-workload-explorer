from types import SimpleNamespace

import pytest

from app.services.illumio_write_back_service import IllumioWriteBackService
from app.services.illumio_write_back_service import _FIELD_TO_LABEL_KEY
from app.config import settings


def result(**values):
    defaults = {
        "id": 1, "field_name": "application", "illumio_value": "billing",
        "cmdb_value": "orders",
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_write_back_uses_canonical_reconciliation_field_names():
    class Client:
        def find_or_create_label(self, key, value):
            assert (key, value) == ("application", "orders")
            return "/orgs/1/labels/1"

    labels = IllumioWriteBackService._apply_label_changes(
        [{"key": "application", "value": "billing", "href": "/orgs/1/labels/old"}],
        [result()], Client(),
    )
    assert labels == [{"href": "/orgs/1/labels/1"}]


def test_write_back_rejects_stale_pce_values_before_put():
    with pytest.raises(ValueError, match="Stale reconciliation result"):
        IllumioWriteBackService._assert_snapshot_is_current(
            {"labels": [{"key": "application", "value": "changed-in-pce"}]},
            [result()],
        )


def test_write_back_accepts_matching_snapshot_and_detects_conflicts():
    IllumioWriteBackService._assert_snapshot_is_current(
        {"labels": [{"key": "application", "value": "billing"}]}, [result()]
    )
    class Client:
        def find_or_create_label(self, key, value):
            return f"/{key}/{value}"

    with pytest.raises(ValueError, match="Conflicting approved values"):
        IllumioWriteBackService._apply_label_changes(
            [], [result(cmdb_value="orders"), result(id=2, cmdb_value="finance")], Client()
        )


def test_preflight_field_mapping_covers_all_canonical_reconciliation_fields():
    assert {"application", "role", "environment", "location"} <= set(_FIELD_TO_LABEL_KEY)


def test_real_client_mode_alone_does_not_enable_pce_writeback(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_USE_REAL_CLIENT", True)
    monkeypatch.setattr(settings, "ILLUMIO_ALLOW_PCE_WRITEBACK", False)
    result = IllumioWriteBackService.apply_approved()
    assert result["applied"] == 0
    assert "disabled" in result["note"]
