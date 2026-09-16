from app.ui.admin_widget import RESET_CONFIRMATION, format_health_report, reset_confirmation_is_valid


def test_admin_reset_requires_the_exact_typed_confirmation():
    assert reset_confirmation_is_valid(RESET_CONFIRMATION)
    assert reset_confirmation_is_valid(f"  {RESET_CONFIRMATION}  ")
    assert not reset_confirmation_is_valid("reset local data")
    assert not reset_confirmation_is_valid("RESET")


def test_admin_health_output_reports_local_state_without_credentials():
    report = {
        "database": "illumio_workloads",
        "real_pce_reads": False,
        "pce_writeback": False,
        "qt_platform_plugin_available": True,
        "pg_dump_available": True,
        "counts": {"illumio_workloads": 40_000},
        "missing_tables": [],
        "missing_indexes": [],
    }

    output = format_health_report(report)

    assert "PCE reads: disabled" in output
    assert "PCE write-back: disabled" in output
    assert "illumio_workloads: 40,000" in output
    assert "password" not in output.casefold()
