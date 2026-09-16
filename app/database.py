from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Ensure all models are registered in SQLAlchemy's mapper registry
# before any session is created or any relationship is resolved.
import app.models.illumio  # noqa: F401
import app.models.cmdb_ci  # noqa: F401
import app.models.cmdb_import_run  # noqa: F401
import app.models.cmdb_staging_ci  # noqa: F401
import app.models.reconciliation_result  # noqa: F401
import app.models.reconciliation_run  # noqa: F401
# Legacy models remain available through disabled tabs. Register their whole
# foreign-key graph too, so importing the desktop entry point cannot leave
# SQLAlchemy metadata in a partially resolvable state.
import app.models.import_run  # noqa: F401
import app.models.workload  # noqa: F401
import app.models.workload_ip  # noqa: F401
import app.models.automation  # noqa: F401


DATABASE_URL = settings.DATABASE_URL or (
    f"postgresql+psycopg2://"
    f"{settings.DB_USER}:"
    f"{settings.DB_PASSWORD}@"
    f"{settings.DB_HOST}:"
    f"{settings.DB_PORT}/"
    f"{settings.DB_NAME}"
)

if DATABASE_URL.startswith("sqlite"):
    # Test-only support.  Production remains PostgreSQL and uses the pool below.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        # Keep connections alive in a pool — avoids paying TCP setup cost
        # on every button click. 10 connections is plenty for a desktop app.
        pool_size=10,
        max_overflow=5,
        pool_timeout=30,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


_VALID_TABLES = frozenset({
    "illumio_workloads",
    "illumio_interfaces",
    "illumio_labels",
    "illumio_workload_labels",
    "cmdb_cis",
    "cmdb_staging_cis",
    "cmdb_import_runs",
    "reconciliation_runs",
    "reconciliation_results",
    "workloads",
    "workload_ips",
    "workload_changes",
    "import_runs",
    "automations",
    "delivery_recipients",
    "delivery_subscriptions",
    "automation_runs",
    "ingestion_sources",
    "sync_runs",
})


def analyze_tables(*table_names):
    """
    Run ANALYZE on the given table names so the Postgres query planner has
    up-to-date statistics after a bulk load.  Safe to call from a background
    thread — opens and immediately closes its own connection.

    Usage:
        analyze_tables("illumio_workloads", "illumio_interfaces")
    """
    with engine.connect() as conn:
        for table in table_names:
            if table not in _VALID_TABLES:
                raise ValueError(f"Unknown or unauthorized table name for ANALYZE: {table!r}")
            conn.execute(__import__("sqlalchemy").text(f"ANALYZE {table}"))
        conn.commit()


def ensure_performance_indexes():
    """Create Phase 5 additive indexes on existing development databases.

    These calls are idempotent and must be formalized in the upcoming Alembic
    migration phase. They are intentionally limited to indexes justified by
    the active Workloads and Reconciliation query shapes.
    """
    from app.models.illumio.illumio_workload import IllumioWorkload
    from app.models.reconciliation_result import ReconciliationResult

    for index in (*IllumioWorkload.__table__.indexes, *ReconciliationResult.__table__.indexes):
        if index.name in {
            "ix_illumio_workloads_online_enforcement_hostname",
            "ix_reconciliation_results_run_filters_hostname",
            "ix_reconciliation_results_run_hostname",
        }:
            index.create(bind=engine, checkfirst=True)
