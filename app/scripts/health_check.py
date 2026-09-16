"""Read-only local readiness check for the Illumio Workload Explorer."""

from sqlalchemy import inspect, text
from pathlib import Path
import platform
import shutil

import PySide6
from PySide6.QtCore import QLibraryInfo

from app.config import settings
from app.database import engine


_TABLES = {
    "illumio_workloads", "illumio_interfaces", "illumio_labels", "illumio_workload_labels",
    "cmdb_cis", "cmdb_import_runs", "reconciliation_runs", "reconciliation_results",
}
_INDEXES = {
    "ix_illumio_workloads_online_enforcement_hostname",
    "ix_reconciliation_results_run_filters_hostname",
    "ix_reconciliation_results_run_hostname",
}
_QT_PLATFORM_PLUGINS = {
    "Darwin": "libqcocoa.dylib",
    "Windows": "qwindows.dll",
    "Linux": "libqxcb.so",
}


def expected_qt_platform_plugin(platform_name: str | None = None) -> str:
    """Return the normal Qt platform plugin for the current desktop OS."""
    return _QT_PLATFORM_PLUGINS.get(platform_name or platform.system(), "")


def qt_platform_plugin_path(platform_name: str | None = None) -> Path:
    plugin_name = expected_qt_platform_plugin(platform_name)
    return Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platforms" / plugin_name


def collect_health():
    platform_name = platform.system()
    qt_plugin_name = expected_qt_platform_plugin(platform_name)
    qt_plugin_path = qt_platform_plugin_path(platform_name)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_tables = sorted(_TABLES - tables)
    indexes = {
        index["name"]
        for table in ("illumio_workloads", "reconciliation_results")
        if table in tables
        for index in inspector.get_indexes(table)
    }
    missing_indexes = sorted(_INDEXES - indexes)
    counts = {}
    with engine.connect() as connection:
        for table in sorted(_TABLES & tables):
            if table not in _TABLES:
                continue
            counts[table] = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
    return {
        "database": engine.url.database,
        "missing_tables": missing_tables,
        "missing_indexes": missing_indexes,
        "counts": counts,
        "real_pce_reads": settings.ILLUMIO_USE_REAL_CLIENT,
        "pce_writeback": settings.ILLUMIO_ALLOW_PCE_WRITEBACK,
        "qt_version": PySide6.__version__,
        "platform": platform_name,
        "qt_platform_plugin": qt_plugin_name,
        "qt_platform_plugin_available": bool(qt_plugin_name) and qt_plugin_path.is_file(),
        "pg_dump_available": shutil.which("pg_dump") is not None,
    }


def main():
    report = collect_health()
    print(f"Database: {report['database']}")
    print(f"Real PCE reads: {'enabled' if report['real_pce_reads'] else 'disabled'}")
    print(f"PCE write-back: {'enabled' if report['pce_writeback'] else 'disabled'}")
    print(
        f"PySide6: {report['qt_version']}  |  {report['platform']} Qt plugin "
        f"({report['qt_platform_plugin'] or 'unknown'}): "
        f"{'present' if report['qt_platform_plugin_available'] else 'missing'}"
    )
    print(f"pg_dump: {'available' if report['pg_dump_available'] else 'not found (backups unavailable)'}")
    for table, count in report["counts"].items():
        print(f"{table}: {count:,} rows")
    if report["missing_tables"] or report["missing_indexes"] or not report["qt_platform_plugin_available"]:
        if report["missing_tables"]:
            print("Missing tables: " + ", ".join(report["missing_tables"]))
        if report["missing_indexes"]:
            print("Missing indexes: " + ", ".join(report["missing_indexes"]))
        if not report["qt_platform_plugin_available"]:
            print("Missing native Qt platform plugin; reinstall the project virtual environment.")
        raise SystemExit(1)
    print("Health check passed.")


if __name__ == "__main__":
    main()
