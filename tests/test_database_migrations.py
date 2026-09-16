from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = PROJECT_ROOT / "migrations" / "versions" / "20260902_01_performance_indexes.py"


def test_database_migration_tracks_all_paged_browser_indexes():
    contents = MIGRATION.read_text()

    assert "CREATE INDEX IF NOT EXISTS" in contents
    assert "ix_illumio_workloads_online_enforcement_hostname" in contents
    assert "ix_reconciliation_results_run_filters_hostname" in contents
    assert "ix_reconciliation_results_run_hostname" in contents
    assert "run_id, status, resolution_action, field_name, hostname" in contents
    assert "match_status" not in contents
    assert "DELETE" not in contents
    assert "TRUNCATE" not in contents


def test_alembic_configuration_is_present_for_future_native_releases():
    contents = (PROJECT_ROOT / "alembic.ini").read_text()

    assert "script_location = migrations" in contents


def test_automation_migration_is_additive_and_has_no_credentials():
    contents = (
        PROJECT_ROOT / "migrations" / "versions" / "20260914_02_automation_foundation.py"
    ).read_text()

    assert '"automations"' in contents
    assert '"delivery_recipients"' in contents
    assert '"automation_runs"' in contents
    assert "password" not in contents.casefold()
    assert "access_token" not in contents.casefold()
