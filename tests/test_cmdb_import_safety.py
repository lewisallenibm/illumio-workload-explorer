import csv

import pytest

from app.database import SessionLocal
from app.models.cmdb_ci import CmdbCi
from app.models.cmdb_import_run import CmdbImportRun
from app.models.reconciliation_result import ReconciliationResult
from app.repositories.cmdb_repository import CmdbRepository
from app.services.cmdb_import_service import CmdbImportService, CmdbValidationError
from app.services.mock_cmdb_sync_service import MockCmdbSyncService


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def active_hostnames():
    session = SessionLocal()
    try:
        return [row[0] for row in session.query(CmdbCi.hostname).order_by(CmdbCi.hostname).all()]
    finally:
        session.close()


def seed_old_snapshot():
    session = SessionLocal()
    try:
        session.add(CmdbCi(hostname="old-host", cmdb_app="old-app"))
        session.commit()
    finally:
        session.close()


def test_inventory_aliases_unknown_columns_and_provenance(tmp_path):
    path = tmp_path / "inventory.csv"
    write_csv(path, ["MachineName", "PCE App", "PCE Role", "PCE Env", "PCE Loc", "VEN installed?", "Custom"], [{
        "MachineName": "server01", "PCE App": "orders", "PCE Role": "web",
        "PCE Env": "prod", "PCE Loc": "east", "VEN installed?": "yes", "Custom": "retain",
    }])

    preview = CmdbImportService.preview(path)
    assert preview.valid
    assert preview.identifier_strategy == "normalized hostname"
    assert "cmdb_app" in preview.recognized_headers
    assert preview.unknown_headers == ("Custom",)

    result = CmdbImportService.import_file(path)
    assert (result["inserted"], result["rejected"], result["duplicates"]) == (1, 0, 0)
    session = SessionLocal()
    try:
        ci = session.query(CmdbCi).one()
        assert (ci.cmdb_app, ci.cmdb_role, ci.cmdb_env, ci.cmdb_loc) == ("orders", "web", "prod", "east")
        assert ci.ven_installed is True
        assert ci.extra_fields == {"Custom": "retain"}
        run = session.query(CmdbImportRun).one()
        assert (run.source_type, run.source_filename, run.status) == ("inventory_csv", "inventory.csv", "SUCCESS")
    finally:
        session.close()
    assert CmdbRepository.latest_import_metadata().records_inserted == 1


def test_invalid_headers_and_malformed_rows_preserve_active_snapshot(tmp_path):
    seed_old_snapshot()
    invalid = tmp_path / "invalid.csv"
    write_csv(invalid, ["not_a_cmdb_identifier"], [{"not_a_cmdb_identifier": "x"}])
    with pytest.raises(CmdbValidationError):
        CmdbImportService.import_file(invalid)
    assert active_hostnames() == ["old-host"]

    malformed = tmp_path / "malformed.csv"
    write_csv(malformed, ["hostname", "app"], [{"hostname": "", "app": "orders"}])
    with pytest.raises(CmdbValidationError):
        CmdbImportService.import_file(malformed)
    assert active_hostnames() == ["old-host"]


def test_successful_snapshot_replacement_changes_active_dataset(tmp_path):
    seed_old_snapshot()
    path = tmp_path / "new.csv"
    write_csv(path, ["hostname", "application"], [{"hostname": "new-host", "application": "new-app"}])

    CmdbImportService.import_file(path)

    assert active_hostnames() == ["new-host"]


def test_duplicate_hostname_identity_is_retained_and_reported(tmp_path):
    path = tmp_path / "duplicates.csv"
    write_csv(path, ["hostname", "application"], [
        {"hostname": "server01", "application": "first"},
        {"hostname": "SERVER01", "application": "second"},
    ])

    preview = CmdbImportService.preview(path)
    assert preview.valid
    assert preview.duplicate_identities == 1
    result = CmdbImportService.import_file(path)
    assert result["duplicates"] == 1
    assert active_hostnames() == ["SERVER01", "server01"]


def test_streaming_csv_uses_chunked_persistence(tmp_path):
    path = tmp_path / "large.csv"
    rows = [{"hostname": f"host-{index:04d}"} for index in range(2_050)]
    write_csv(path, ["hostname"], rows)
    progress = []

    result = CmdbImportService.import_file(path, progress_callback=lambda done, total: progress.append((done, total)))

    assert result["inserted"] == 2_050
    assert progress == [(1_000, 2_050), (2_000, 2_050)]


def test_mock_snapshot_creates_current_domain_provenance():
    result = MockCmdbSyncService.sync(count=12)
    assert result["source_type"] == "mock_cmdb"
    assert active_hostnames()
    metadata = CmdbRepository.latest_import_metadata()
    assert metadata.source_type == "mock_cmdb"
    assert metadata.records_inserted == 12


def test_replacement_detaches_legacy_result_reference_and_preserves_evidence(tmp_path):
    seed_old_snapshot()
    session = SessionLocal()
    try:
        old = session.query(CmdbCi).one()
        session.add(ReconciliationResult(cmdb_ci_id=old.id, hostname="old-host", status="mismatch"))
        session.commit()
    finally:
        session.close()
    path = tmp_path / "new.csv"
    write_csv(path, ["hostname"], [{"hostname": "new-host"}])

    CmdbImportService.import_file(path)

    assert active_hostnames() == ["new-host"]
    session = SessionLocal()
    try:
        result = session.query(ReconciliationResult).one()
        assert (result.cmdb_ci_id, result.hostname, result.status) == (None, "old-host", "mismatch")
    finally:
        session.close()
