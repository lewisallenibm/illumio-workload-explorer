import csv

import pytest

from app.database import SessionLocal
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_workload import IllumioWorkload
from app.repositories.illumio_workload_repository import IllumioWorkloadRepository
from app.services.illumio.ingestion_service import IllumioIngestionService
from app.services.illumio.workloader_source_adapter import (
    WorkloaderCsvSourceAdapter,
    WorkloaderValidationError,
)


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_valid_workloader_csv_maps_aliases_and_preserves_unknown_columns(tmp_path):
    path = tmp_path / "export.csv"
    write_csv(path, ["MachineName", "App", "ENV", "LOC", "public IP", "Mystery Field"], [{
        "MachineName": "Server01.Example.Test",
        "App": "orders", "ENV": "prod", "LOC": "east",
        "public IP": "203.0.113.10", "Mystery Field": "retain me",
    }])

    preview, records = WorkloaderCsvSourceAdapter.load_records(path)

    assert preview.valid
    assert preview.identifier == "hostname/name fallback"
    assert {"hostname", "application", "environment", "location", "public_ip"} <= set(preview.known_columns)
    assert preview.unknown_columns == ("Mystery Field",)
    assert records[0]["href"].startswith("workloader://hostname/")
    assert records[0]["raw_json"]["Mystery Field"] == "retain me"
    assert {label["type"] for label in records[0]["labels"]} == {
        "application", "environment", "location"
    }
    assert records[0]["interfaces"][0]["address"] == "203.0.113.10"


def test_preview_rejects_missing_identity_and_duplicate_fallback_identity(tmp_path):
    no_identifier = tmp_path / "no-id.csv"
    write_csv(no_identifier, ["App"], [{"App": "orders"}])
    preview = WorkloaderCsvSourceAdapter.preview(no_identifier)
    assert not preview.valid
    assert "No usable workload identifier" in preview.errors[0]

    duplicate = tmp_path / "duplicate.csv"
    write_csv(duplicate, ["hostname"], [{"hostname": "server01"}, {"hostname": "SERVER01"}])
    preview = WorkloaderCsvSourceAdapter.preview(duplicate)
    assert not preview.valid
    assert preview.malformed_rows == 1
    with pytest.raises(WorkloaderValidationError):
        WorkloaderCsvSourceAdapter.load_records(duplicate)


def test_preview_accepts_ven_href_as_a_last_resort_stable_identifier(tmp_path):
    path = tmp_path / "ven-only.csv"
    write_csv(path, ["VEN Href", "agent_version"], [{
        "VEN Href": "/orgs/1/vens/abc", "agent_version": "24.2",
    }])

    preview, records = WorkloaderCsvSourceAdapter.load_records(path)

    assert preview.valid
    assert preview.identifier == "VEN href fallback"
    assert records[0]["href"].startswith("workloader://ven/")


def test_preview_reports_malformed_csv(tmp_path):
    path = tmp_path / "broken.csv"
    path.write_text('hostname,app\n"unterminated,orders\n', encoding="utf-8")

    preview = WorkloaderCsvSourceAdapter.preview(path)

    assert not preview.valid
    assert preview.errors[0].startswith("Unable to parse CSV")


def test_workloader_import_uses_shared_ingestion_is_idempotent_and_updates(tmp_path):
    path = tmp_path / "workloader.csv"
    headers = ["href", "hostname", "application", "role", "interfaces", "agent_version"]
    write_csv(path, headers, [{
        "href": "/orgs/1/workloads/abc", "hostname": "server01",
        "application": "orders", "role": "web",
        "interfaces": '[{"name": "eth0", "address": "10.0.0.10"}]', "agent_version": "24.1",
    }])

    preview, records = WorkloaderCsvSourceAdapter.load_records(path)
    first = IllumioIngestionService.ingest(
        records, source=WorkloaderCsvSourceAdapter.source_type, source_filename=preview.filename
    )
    assert (first["inserted"], first["updated"], first["failed"]) == (1, 0, 0)
    assert IllumioIngestionService.ingest(records, source="workloader_csv", source_filename=preview.filename)["updated"] == 0

    write_csv(path, headers, [{
        "href": "/orgs/1/workloads/abc", "hostname": "server01",
        "application": "billing", "role": "web",
        "interfaces": '[{"name": "eth1", "address": "10.0.0.20"}]', "agent_version": "24.2",
    }])
    _, changed_records = WorkloaderCsvSourceAdapter.load_records(path)
    changed = IllumioIngestionService.ingest(changed_records, source="workloader_csv", source_filename=preview.filename)
    assert (changed["inserted"], changed["updated"], changed["failed"]) == (0, 1, 0)

    session = SessionLocal()
    try:
        workload = session.query(IllumioWorkload).one()
        assert workload.ven_version == "24.2"
        assert [interface.ip_address for interface in session.query(IllumioInterface).all()] == ["10.0.0.20"]
    finally:
        session.close()

    metadata = IllumioWorkloadRepository.latest_ingestion_metadata()
    assert metadata[0].source_type == "workloader_csv"
    assert metadata[0].source_filename == "workloader.csv"


def test_detail_repository_returns_preloaded_labels_and_interfaces(tmp_path):
    path = tmp_path / "detail.csv"
    write_csv(path, ["href", "hostname", "app", "public_ip"], [{
        "href": "/orgs/1/workloads/detail", "hostname": "detail-host",
        "app": "orders", "public_ip": "203.0.113.44",
    }])
    _, records = WorkloaderCsvSourceAdapter.load_records(path)
    IllumioIngestionService.ingest(records, source="workloader_csv", source_filename=path.name)

    session = SessionLocal()
    try:
        workload_id = session.query(IllumioWorkload.id).scalar()
    finally:
        session.close()
    detail = IllumioWorkloadRepository.get_by_id(workload_id)

    assert detail.hostname == "detail-host"
    assert [(item.label.label_type, item.label.value) for item in detail.labels] == [("application", "orders")]
    assert [(item.interface_name, item.ip_address) for item in detail.interfaces] == [("public", "203.0.113.44")]
