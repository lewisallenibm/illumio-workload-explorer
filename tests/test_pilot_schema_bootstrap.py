"""Schema coverage needed for a fresh packaged pilot workspace."""


def test_main_imports_every_model_required_for_a_fresh_pilot_schema(monkeypatch):
    # A source import must remain a normal development launch; the test only
    # verifies that the app's model metadata is complete before first-launch
    # Base.metadata.create_all() runs inside a frozen pilot package.
    monkeypatch.delenv("ILLUMIO_MANAGED_WORKSPACE", raising=False)

    import app.main  # noqa: F401
    from app.models.base import Base

    required = {
        "illumio_workloads",
        "illumio_interfaces",
        "illumio_labels",
        "illumio_workload_labels",
        "cmdb_cis",
        "cmdb_import_runs",
        "reconciliation_runs",
        "reconciliation_results",
    }

    assert required <= set(Base.metadata.tables)
