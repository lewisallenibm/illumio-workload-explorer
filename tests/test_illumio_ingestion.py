import pytest

from app.database import SessionLocal
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_label import IllumioLabel
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.models.illumio.sync_run import SyncRun
from app.services.illumio.ingestion_service import IllumioIngestionService
from app.services.illumio.mock_data_generator import MockDataGenerator
from app.services.illumio.normalization import normalize_workload
from app.services.illumio.real_illumio_client import RealIllumioClient
from app.config import settings


def workload_record(**overrides):
    record = {
        "href": "/orgs/1/workloads/one",
        "name": "server01",
        "hostname": "server01.example.test",
        "online": True,
        "enforcement_mode": "visibility",
        "visibility": "flow_summary",
        "agent_version": "24.2.0",
        "os_id": "rhel",
        "os_detail": "RHEL 9",
        "interfaces": [{"name": "eth0", "addresses": ["10.0.0.10"]}],
        "labels": [
            {"href": "/orgs/1/labels/a", "key": "app", "value": "orders"},
            {"href": "/orgs/1/labels/r", "key": "role", "value": "web"},
            {"href": "/orgs/1/labels/e", "key": "env", "value": "prod"},
            {"href": "/orgs/1/labels/l", "key": "loc", "value": "east"},
        ],
    }
    record.update(overrides)
    return record


def test_normalization_uses_one_label_vocabulary_and_preserves_raw_data():
    record = normalize_workload(workload_record())

    assert [label.key for label in record.labels] == [
        "application", "role", "environment", "location"
    ]
    assert record.ven_version == "24.2.0"
    assert record.visibility_status == "flow_summary"
    assert record.interfaces[0].address == "10.0.0.10"
    assert record.raw["hostname"] == "server01.example.test"


def test_mock_label_hrefs_are_stable_for_each_label_value():
    records = MockDataGenerator.generate(count=250, random_seed=7)
    href_values = {}

    for record in records:
        for label in record["labels"]:
            key = label["href"]
            value = (label["type"], label["value"])
            assert href_values.setdefault(key, value) == value


def test_mock_payload_uses_the_shared_ingestion_path_without_label_collisions():
    records = MockDataGenerator.generate(count=50, random_seed=7)
    result = IllumioIngestionService.ingest(records, source="mock")

    assert (result["inserted"], result["updated"], result["failed"]) == (50, 0, 0)


def test_ingestion_inserts_normalized_workload_interfaces_and_labels():
    result = IllumioIngestionService.ingest([workload_record()], source="test")

    assert result == {
        "status": "SUCCESS", "source": "test", "received": 1,
        "inserted": 1, "updated": 0, "failed": 0,
    }
    session = SessionLocal()
    try:
        workload = session.query(IllumioWorkload).one()
        assert workload.hostname == "server01.example.test"
        assert workload.enforcement_mode == "visibility"
        assert workload.visibility_status == "flow_summary"
        assert session.query(IllumioInterface).count() == 1
        assert session.query(IllumioLabel).count() == 4
        assert session.query(IllumioWorkloadLabel).count() == 4
        run = session.query(SyncRun).one()
        assert (run.records_inserted, run.records_updated, run.records_failed) == (1, 0, 0)
    finally:
        session.close()


def test_ingestion_updates_existing_workload_and_is_idempotent():
    first = workload_record()
    assert IllumioIngestionService.ingest([first])["inserted"] == 1

    changed = workload_record(
        enforcement_mode="full",
        interfaces=[{"name": "eth1", "address": "10.0.0.20"}],
        labels=[{"href": "/orgs/1/labels/a", "type": "application", "value": "billing"}],
    )
    result = IllumioIngestionService.ingest([changed])
    assert (result["inserted"], result["updated"], result["failed"]) == (0, 1, 0)

    repeat = IllumioIngestionService.ingest([changed])
    assert (repeat["inserted"], repeat["updated"], repeat["failed"]) == (0, 0, 0)

    session = SessionLocal()
    try:
        workload = session.query(IllumioWorkload).one()
        assert workload.enforcement_mode == "full"
        assert [row.ip_address for row in session.query(IllumioInterface).all()] == ["10.0.0.20"]
        assert [(row.label_type, row.value) for row in session.query(IllumioLabel).all() if row.illumio_href == "/orgs/1/labels/a"] == [("application", "billing")]
        assert session.query(IllumioWorkloadLabel).count() == 1
    finally:
        session.close()


def test_malformed_record_is_counted_without_losing_valid_records():
    result = IllumioIngestionService.ingest([
        workload_record(),
        {"hostname": "missing-identifier"},
    ])

    assert (result["inserted"], result["updated"], result["failed"]) == (1, 0, 1)
    assert result["status"] == "COMPLETED_WITH_ERRORS"
    session = SessionLocal()
    try:
        assert session.query(IllumioWorkload).count() == 1
        run = session.query(SyncRun).one()
        assert run.status == "COMPLETED_WITH_ERRORS"
    finally:
        session.close()


def test_real_client_converts_pce_hrefs_to_org_relative_paths():
    client = RealIllumioClient()

    assert client._path_from_href("/orgs/1/workloads/abc") == "/workloads/abc"
    assert client._path_from_href("/api/v2/orgs/1/workloads/abc") == "/workloads/abc"


def test_real_client_rejects_invalid_pce_configuration_before_request(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_PCE_HOST", "https://pce.example.test")
    monkeypatch.setattr(settings, "ILLUMIO_API_KEY_ID", "id")
    monkeypatch.setattr(settings, "ILLUMIO_API_KEY_SECRET", "secret")
    with pytest.raises(ValueError, match="hostname only"):
        RealIllumioClient.validate_configuration()


def test_real_client_handles_partial_pce_pages_without_skipping_records(monkeypatch):
    monkeypatch.setattr(settings, "ILLUMIO_PCE_HOST", "pce.example.test")
    monkeypatch.setattr(settings, "ILLUMIO_API_KEY_ID", "id")
    monkeypatch.setattr(settings, "ILLUMIO_API_KEY_SECRET", "secret")
    client = RealIllumioClient()
    requests = []

    class Response:
        def __init__(self, page, total):
            self._page, self.headers = page, {"X-Total-Count": str(total)}

        def json(self):
            return self._page

    pages = [
        Response([workload_record(href="/orgs/1/workloads/1")], 2),
        Response([workload_record(href="/orgs/1/workloads/2")], 2),
    ]
    client._get = lambda path, params: requests.append((path, params)) or pages.pop(0)

    rows = client.get_workloads()
    assert [row["href"] for row in rows] == ["/orgs/1/workloads/1", "/orgs/1/workloads/2"]
    assert [params["offset"] for _, params in requests] == [0, 1]
