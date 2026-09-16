import pytest

from app.database import SessionLocal
from app.models.reconciliation_result import ReconciliationResult
from app.models.reconciliation_run import ReconciliationRun
from app.repositories.cmdb_repository import ReconciliationRepository
from app.services.cmdb_import_service import CmdbImportService
from app.services.illumio.ingestion_service import IllumioIngestionService
from app.services.reconciliation_service import ReconciliationService


def ill_record(hostname, href, labels=None):
    return {
        "href": href, "hostname": hostname, "name": hostname, "online": True,
        "labels": [{"href": f"/orgs/1/labels/{key}-{value}", "type": key, "value": value} for key, value in (labels or {}).items()],
        "interfaces": [],
    }


def cmdb_record(hostname, **labels):
    return {
        "hostname": hostname,
        "cmdb_app": labels.get("application"), "cmdb_role": labels.get("role"),
        "cmdb_env": labels.get("environment"), "cmdb_loc": labels.get("location"),
        "ven_installed": labels.get("ven_installed"),
    }


def reconcile(cmdb_records, illumio_records):
    CmdbImportService.replace_mock_records(cmdb_records)
    IllumioIngestionService.ingest(illumio_records, source="mock")
    return ReconciliationService.run()


def results_for(run_id):
    session = SessionLocal()
    try:
        return session.query(ReconciliationResult).filter(ReconciliationResult.run_id == run_id).all()
    finally:
        session.close()


def test_exact_and_case_whitespace_hostname_match_is_counted_without_persisted_matched_rows():
    result = reconcile(
        [cmdb_record(" Server01. ", application="orders", role="web", environment="prod", location="east")],
        [ill_record("server01", "/orgs/1/workloads/1", {"application": "orders", "role": "web", "environment": "prod", "location": "east"})],
    )
    assert result["matched_workloads"] == 1
    assert results_for(result["run_id"]) == []


def test_unambiguous_short_hostname_matches_fqdn_but_ambiguous_does_not():
    result = reconcile(
        [cmdb_record("server01", application="orders")],
        [ill_record("server01.example.test", "/orgs/1/workloads/1", {"application": "orders"})],
    )
    assert result["matched_workloads"] == 0  # Other three missing expected labels are review rows.
    assert not any(row.status == "MISSING_IN_ILLUMIO" for row in results_for(result["run_id"]))

    result = reconcile(
        [cmdb_record("server01", application="orders")],
        [ill_record("server01.a.test", "/orgs/1/workloads/a"), ill_record("server01.b.test", "/orgs/1/workloads/b")],
    )
    assert any(row.status == "AMBIGUOUS_MATCH" for row in results_for(result["run_id"]))


def test_fqdn_cmdb_matches_a_single_short_illumio_hostname_but_not_another_fqdn():
    result = reconcile(
        [cmdb_record("server01.example.test", application="orders")],
        [ill_record("server01", "/orgs/1/workloads/1", {"application": "orders"})],
    )
    assert not any(row.status == "MISSING_IN_ILLUMIO" for row in results_for(result["run_id"]))

    result = reconcile(
        [cmdb_record("server02.example.test", application="orders")],
        [ill_record("server02.other.test", "/orgs/1/workloads/2", {"application": "orders"})],
    )
    statuses = [row.status for row in results_for(result["run_id"])]
    assert "MISSING_IN_ILLUMIO" in statuses
    assert "ORPHANED_IN_ILLUMIO" in statuses


@pytest.mark.parametrize("field,expected,current,status", [
    ("application", "orders", "billing", "LABEL_MISMATCH"),
    ("role", "web", "db", "LABEL_MISMATCH"),
    ("environment", "prod", "dev", "LABEL_MISMATCH"),
    ("location", "east", "west", "LABEL_MISMATCH"),
])
def test_canonical_label_mismatches(field, expected, current, status):
    result = reconcile(
        [cmdb_record("server", **{field: expected})],
        [ill_record("server", "/orgs/1/workloads/1", {field: current})],
    )
    rows = results_for(result["run_id"])
    assert any(row.field_name == field and row.status == status for row in rows)
    mismatch = next(row for row in rows if row.field_name == field and row.status == status)
    assert mismatch.illumio_href == "/orgs/1/workloads/1"
    assert any(row.status == "NO_EXPECTED_VALUE" for row in rows)


def test_missing_label_and_no_expected_value_are_explicit_and_not_approvable():
    result = reconcile(
        [cmdb_record("server", application="orders")],
        [ill_record("server", "/orgs/1/workloads/1", {})],
    )
    rows = results_for(result["run_id"])
    missing = next(row for row in rows if row.field_name == "application")
    no_expected = next(row for row in rows if row.field_name == "role")
    assert missing.status == "LABEL_MISSING"
    assert no_expected.status == "NO_EXPECTED_VALUE"
    ReconciliationRepository.mark_approved([missing.id, no_expected.id])
    rows = {row.id: row for row in results_for(result["run_id"])}
    assert rows[missing.id].resolution_action == "approved"
    assert rows[no_expected.id].resolution_action == "pending"


def test_missing_orphaned_and_duplicate_groups_are_persisted_as_review_conditions():
    result = reconcile(
        [cmdb_record("missing"), cmdb_record("duplicate"), cmdb_record("DUPLICATE")],
        [ill_record("orphan", "/orgs/1/workloads/o"), ill_record("duplicate", "/orgs/1/workloads/d")],
    )
    rows = results_for(result["run_id"])
    statuses = [row.status for row in rows]
    assert "MISSING_IN_ILLUMIO" in statuses
    assert "ORPHANED_IN_ILLUMIO" in statuses
    assert "AMBIGUOUS_MATCH" in statuses
    restricted = [row for row in rows if row.status in {
        "MISSING_IN_ILLUMIO", "ORPHANED_IN_ILLUMIO", "AMBIGUOUS_MATCH"
    }]
    ReconciliationRepository.mark_approved([row.id for row in restricted])
    assert all(
        row.resolution_action == "pending"
        for row in results_for(result["run_id"])
        if row.id in {item.id for item in restricted}
    )


def test_duplicate_illumio_hostname_is_ambiguous():
    result = reconcile(
        [cmdb_record("server")],
        [ill_record("server", "/orgs/1/workloads/a"), ill_record("SERVER", "/orgs/1/workloads/b")],
    )
    assert any(row.status == "AMBIGUOUS_MATCH" for row in results_for(result["run_id"]))


def test_reruns_create_immutable_history_and_cmdb_b_replaces_snapshot_a():
    first = reconcile(
        [cmdb_record("server", application="orders")],
        [ill_record("server", "/orgs/1/workloads/1", {"application": "billing"})],
    )
    first_rows = results_for(first["run_id"])
    first_mismatch = next(row for row in first_rows if row.field_name == "application")
    assert (first_mismatch.cmdb_value, first_mismatch.illumio_value) == ("orders", "billing")

    # Snapshot B activates successfully despite historical result rows.
    CmdbImportService.replace_mock_records([cmdb_record("server", application="billing")])
    second = ReconciliationService.run()
    assert second["run_id"] != first["run_id"]
    historical = next(row for row in results_for(first["run_id"]) if row.id == first_mismatch.id)
    assert (historical.cmdb_value, historical.illumio_value, historical.cmdb_ci_id) == ("orders", "billing", None)

    session = SessionLocal()
    try:
        assert session.query(ReconciliationRun).count() == 2
    finally:
        session.close()
