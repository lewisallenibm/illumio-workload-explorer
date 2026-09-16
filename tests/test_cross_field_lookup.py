"""Repository coverage for the interactive and bulk cross-field lookups."""

from app.database import SessionLocal
from sqlalchemy import event
from app.database import engine
from app.models.cmdb_ci import CmdbCi
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_label import IllumioLabel
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.repositories.cmdb_repository import CmdbRepository
from app.repositories.illumio_workload_repository import IllumioWorkloadRepository


def test_cmdb_quick_and_bulk_lookup_cover_labels_and_unmapped_ci_identifiers():
    session = SessionLocal()
    try:
        session.add_all([
            CmdbCi(
                hostname="server-one", cmdb_app="A-SECURITY", cmdb_role="R-DB",
                region="Northeast", extra_fields={"sys_id": "ci-12345"},
            ),
            # A repeated hostname represents a source duplicate and must remain
            # visible when a matching label is searched.
            CmdbCi(
                hostname="server-one", cmdb_app="A-SECURITY", cmdb_role="R-DB",
                region="Midwest", extra_fields={"asset_tag": "asset-200"},
            ),
        ])
        session.commit()
    finally:
        session.close()

    assert [row.hostname for row in CmdbRepository.search(search_text="ci-12345")] == ["server-one"]
    bulk = CmdbRepository.bulk_search(["R-DB", "asset-200", "not-present"])

    assert [row.hostname for row in bulk["found"]] == ["server-one", "server-one"]
    assert bulk["missing"] == ["not-present"]


def test_workload_quick_and_bulk_lookup_cover_name_href_and_labels():
    session = SessionLocal()
    try:
        workload = IllumioWorkload(
            hostname="server-one", name="database-node",
            illumio_href="/orgs/1/workloads/ci-12345",
        )
        application = IllumioLabel(id=101, label_type="application", value="A-SECURITY")
        session.add_all([workload, application])
        session.flush()
        session.add_all([
            IllumioInterface(
                workload_id=workload.id, interface_name="eth0", ip_address="10.20.30.40",
            ),
            IllumioWorkloadLabel(workload_id=workload.id, label_id=application.id),
        ])
        session.commit()
    finally:
        session.close()

    assert [row.hostname for row in IllumioWorkloadRepository.search(search_text="A-SECURITY")] == ["server-one"]
    bulk = IllumioWorkloadRepository.bulk_search([
        "database-node", "/orgs/1/workloads/ci-12345", "absent",
    ])

    assert [row.hostname for row in bulk["found"]] == ["server-one"]
    assert bulk["missing"] == ["absent"]


def test_cmdb_bulk_lookup_batches_large_exact_hostname_lists():
    hostnames = [f"bulk-host-{number:04d}" for number in range(501)]
    session = SessionLocal()
    try:
        session.bulk_save_objects([CmdbCi(hostname=hostname) for hostname in hostnames])
        session.commit()
    finally:
        session.close()

    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = CmdbRepository.bulk_search(hostnames)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert len(result["found"]) == len(hostnames)
    assert result["missing"] == []
    # Two exact batches plus two bounded result fetches — never one query per term.
    assert len(statements) <= 4
