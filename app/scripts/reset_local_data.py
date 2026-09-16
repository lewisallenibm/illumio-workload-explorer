"""Guarded reset of local PostgreSQL snapshots; never contacts the PCE."""

import argparse

from sqlalchemy import text

from app.database import engine


_TABLES = (
    "reconciliation_results", "reconciliation_runs", "cmdb_import_staging",
    "cmdb_import_runs", "cmdb_cis", "ingestion_sources", "sync_runs",
    "illumio_workload_labels", "illumio_interfaces", "illumio_labels", "illumio_workloads",
)


def reset_statement():
    return "TRUNCATE TABLE " + ", ".join(_TABLES) + " RESTART IDENTITY CASCADE"


def reset_local_data():
    if not engine.url.drivername.startswith("postgresql"):
        raise ValueError("Local reset utility requires PostgreSQL")
    with engine.begin() as connection:
        connection.execute(text(reset_statement()))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Permanently clear local app snapshots and history.")
    parser.add_argument("--yes", action="store_true", help="confirm the irreversible local reset")
    args = parser.parse_args(argv)
    if not args.yes:
        parser.error("Refusing to reset. Create a backup first, then rerun with --yes.")
    reset_local_data()
    print("Local PostgreSQL app data was reset. No PCE data was changed.")


if __name__ == "__main__":
    main()
