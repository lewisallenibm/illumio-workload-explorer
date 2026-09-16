import pytest

from app.startup_readiness import StartupReadinessError, startup_recovery_message, validate_local_startup


def ready_report(**changes):
    report = {
        "missing_tables": [], "missing_indexes": [], "qt_platform_plugin_available": True,
    }
    report.update(changes)
    return report


def test_startup_readiness_runs_index_setup_then_accepts_healthy_local_install():
    calls = []
    result = validate_local_startup(lambda: calls.append("indexes"), lambda: ready_report())
    assert calls == ["indexes"]
    assert result["missing_tables"] == []


@pytest.mark.parametrize("report", [
    ready_report(missing_tables=["cmdb_cis"]),
    ready_report(missing_indexes=["ix_reconciliation_results_run_hostname"]),
    ready_report(qt_platform_plugin_available=False),
])
def test_startup_readiness_rejects_incomplete_local_install(report):
    with pytest.raises(StartupReadinessError):
        validate_local_startup(lambda: None, lambda: report)


def test_startup_recovery_message_is_safe_and_actionable():
    message = startup_recovery_message()
    assert "PostgreSQL" in message
    assert "data was not changed" in message
    assert "password" not in message.casefold()
