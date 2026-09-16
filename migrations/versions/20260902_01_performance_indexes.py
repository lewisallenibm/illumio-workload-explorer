"""Formalize performance indexes used by the paged desktop browsers.

This revision is additive and safe for the existing local database.  It does
not alter or delete application data.
"""

from alembic import op


revision = "20260902_01"
down_revision = None
branch_labels = None
depends_on = None


_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_illumio_workloads_online_enforcement_hostname "
    "ON illumio_workloads (online, enforcement_mode, hostname)",
    "CREATE INDEX IF NOT EXISTS ix_reconciliation_results_run_filters_hostname "
    "ON reconciliation_results (run_id, status, resolution_action, field_name, hostname)",
    "CREATE INDEX IF NOT EXISTS ix_reconciliation_results_run_hostname "
    "ON reconciliation_results (run_id, hostname)",
)


def upgrade() -> None:
    for statement in _INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Downgrade intentionally only removes additive indexes; it never removes
    # snapshots, runs, reconciliation results, or any other user data.
    for index_name in (
        "ix_reconciliation_results_run_hostname",
        "ix_reconciliation_results_run_filters_hostname",
        "ix_illumio_workloads_online_enforcement_hostname",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
