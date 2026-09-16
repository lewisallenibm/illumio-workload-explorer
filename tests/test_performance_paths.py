"""Fast regression checks for the active browser query paths.

These deliberately use tiny isolated SQLite fixtures.  They assert query
shape and bounded query counts rather than acting as timing benchmarks.
"""

from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models.cmdb_ci import CmdbCi
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.reconciliation_result import ReconciliationResult
from app.repositories.cmdb_repository import CmdbRepository, ReconciliationRepository
from app.repositories.illumio_workload_repository import IllumioWorkloadRepository
from app.ui.cmdb_widget import _PageWorker as CmdbPageWorker
from app.ui.reconciliation_widget import _PageWorker as ReconciliationPageWorker


def _query_counter():
    statements = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    return statements, record


def test_page_queries_are_limited_and_projected():
    session = SessionLocal()
    try:
        session.bulk_save_objects([
            CmdbCi(hostname=f"host-{number:04d}", cmdb_app="orders")
            for number in range(125)
        ])
        session.commit()
    finally:
        session.close()

    rows = CmdbRepository.search(app="orders", limit=25, offset=50)

    assert len(rows) == 25
    assert rows[0].hostname == "host-0050"
    # Repository returns a lightweight projected row, rather than whole ORM
    # entities (which would include extra_fields and other unused columns).
    assert not hasattr(rows[0], "extra_fields")


def test_bulk_lookup_fallback_is_batched_not_per_term():
    session = SessionLocal()
    try:
        workload = IllumioWorkload(hostname="target-host")
        session.add(workload)
        session.flush()
        session.add(IllumioInterface(
            workload_id=workload.id, interface_name="eth0", ip_address="10.20.30.40"
        ))
        session.commit()
    finally:
        session.close()

    # 251 unmatched terms requires two fallback batches, not 502 individual
    # hostname/IP ILIKE queries. One partial match also exercises final fetch.
    terms = [f"missing-{number}" for number in range(250)] + ["target"]
    statements, record = _query_counter()
    try:
        result = IllumioWorkloadRepository.bulk_search(terms)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert [workload.hostname for workload in result["found"]] == ["target-host"]
    assert len(result["missing"]) == 250
    # Exact hostname, interface IP, and label lookups; two set-based fallback
    # batches; then one final ID fetch. No per-term query loop is allowed.
    assert len(statements) <= 6


def test_detail_load_uses_bounded_selectin_queries():
    session = SessionLocal()
    try:
        workload = IllumioWorkload(hostname="detail-host")
        session.add(workload)
        session.flush()
        session.add_all([
            IllumioInterface(workload_id=workload.id, interface_name="eth0", ip_address="10.0.0.1"),
            IllumioInterface(workload_id=workload.id, interface_name="eth1", ip_address="10.0.0.2"),
        ])
        session.commit()
        workload_id = workload.id
    finally:
        session.close()

    statements, record = _query_counter()
    try:
        detail = IllumioWorkloadRepository.get_by_id(workload_id)
        assert [interface.ip_address for interface in detail.interfaces] == ["10.0.0.1", "10.0.0.2"]
    finally:
        event.remove(engine, "before_cursor_execute", record)

    # workload + interfaces + workload labels; label rows are only queried
    # when there are labels to resolve.
    assert len(statements) <= 4


def test_reconciliation_queries_are_scoped_to_requested_run():
    session = SessionLocal()
    try:
        session.add_all([
            ReconciliationResult(run_id=11, hostname="run-eleven", status="LABEL_MISMATCH"),
            ReconciliationResult(run_id=12, hostname="run-twelve", status="LABEL_MISMATCH"),
        ])
        session.commit()
    finally:
        session.close()

    statements, record = _query_counter()
    try:
        rows = ReconciliationRepository.search(run_id=12, limit=50)
        total = ReconciliationRepository.count(run_id=12)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert [row.hostname for row in rows] == ["run-twelve"]
    assert total == 1
    assert all("reconciliation_results.run_id" in statement for statement in statements)


def test_page_workers_reuse_cached_counts(monkeypatch):
    cmdb_rows = []
    recon_rows = []
    monkeypatch.setattr(CmdbRepository, "count", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("count used")))
    monkeypatch.setattr(CmdbRepository, "total_count", lambda: (_ for _ in ()).throw(AssertionError("total used")))
    monkeypatch.setattr(CmdbRepository, "search", lambda **_kwargs: cmdb_rows)
    cmdb_worker = CmdbPageWorker(None, None, None, 500, 500, cached_total=900, cached_db_total=1000)
    cmdb_result = []
    cmdb_worker.finished.connect(lambda total, database_total, rows: cmdb_result.append((total, database_total, rows)))
    cmdb_worker.run()

    monkeypatch.setattr(ReconciliationRepository, "count", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("count used")))
    monkeypatch.setattr(ReconciliationRepository, "search", lambda **_kwargs: recon_rows)
    recon_worker = ReconciliationPageWorker("All", "All", "All", None, 4, 500, 500, cached_total=800)
    recon_result = []
    recon_worker.finished.connect(lambda total, rows: recon_result.append((total, rows)))
    recon_worker.run()

    assert cmdb_result == [(900, 1000, cmdb_rows)]
    assert recon_result == [(800, recon_rows)]
