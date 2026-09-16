import pytest

from app.scripts.reset_local_data import main, reset_statement


def test_reset_requires_an_explicit_confirmation_flag():
    with pytest.raises(SystemExit):
        main([])


def test_reset_statement_is_scoped_to_local_active_snapshot_tables():
    statement = reset_statement()
    assert statement.startswith("TRUNCATE TABLE reconciliation_results")
    assert "illumio_workloads" in statement
    assert statement.endswith("RESTART IDENTITY CASCADE")
