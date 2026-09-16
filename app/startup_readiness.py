"""Friendly local startup validation for a newly installed desktop app."""


class StartupReadinessError(RuntimeError):
    pass


def validate_local_startup(index_setup, health_check):
    """Check local database/Qt readiness before constructing application tabs."""
    index_setup()
    report = health_check()
    problems = []
    if report["missing_tables"]:
        problems.append("database tables are missing")
    if report["missing_indexes"]:
        problems.append("performance indexes are missing")
    if not report["qt_platform_plugin_available"]:
        problems.append("the native Qt display component is missing")
    if problems:
        raise StartupReadinessError("; ".join(problems))
    return report


def startup_recovery_message() -> str:
    return (
        "The app could not prepare its local workspace. Your data was not changed.\n\n"
        "Check that local PostgreSQL is running, then run the Local Health Check. "
        "For a new database, create the schema and apply database upgrades before reopening the app. "
        "Technical details were saved in the private application log."
    )
