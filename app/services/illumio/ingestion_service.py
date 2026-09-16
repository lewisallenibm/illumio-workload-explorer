"""Shared persistence for normalized Illumio workloads.

Every source must normalize first, then call this service.  It is intentionally
non-destructive: records absent from an incoming source are retained and only
the rows represented by the completed source payload are inserted or updated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from app.database import SessionLocal, analyze_tables, engine
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_label import IllumioLabel
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.models.illumio.ingestion_source import IngestionSource
from app.models.illumio.sync_run import SyncRun
from app.services.illumio.normalization import CanonicalWorkload, normalize_workload


_WORKLOAD_FIELDS = (
    "name", "hostname", "online", "connectivity_status", "enforcement_mode",
    "visibility_status", "policy_sync_status", "ransomware_exposure",
    "protection_status", "protection_coverage_score", "ven_version", "os",
    "os_release", "raw_json",
)

_BATCH_SIZE = 1_000


def _batches(values, size=_BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _utcnow():
    """Return a UTC instant compatible with the existing naive DB columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class IllumioIngestionService:
    """Upsert canonical workloads and refresh their normalized children."""

    @staticmethod
    def ingest(
        records: Iterable[dict], source: str = "unknown", source_filename: str | None = None,
    ) -> dict:
        records = list(records)
        # Phase 2 provenance table: creating this additive table is safe for
        # existing development databases and does not alter workload rows.
        IngestionSource.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        run = SyncRun(
            started_at=_utcnow(), status="RUNNING", records_received=len(records),
            records_inserted=0, records_updated=0, records_failed=0,
        )
        session.add(run)
        session.commit()
        session.add(IngestionSource(
            sync_run_id=run.id,
            source_type=source,
            source_filename=source_filename,
        ))
        session.commit()

        inserted = updated = failed = 0
        try:
            existing = {
                workload.illumio_href: workload
                for workload in session.query(IllumioWorkload)
                .filter(IllumioWorkload.illumio_href.isnot(None))
                .all()
            }
            label_by_href = {
                label.illumio_href: label
                for label in session.query(IllumioLabel)
                .filter(IllumioLabel.illumio_href.isnot(None))
                .all()
            }
            label_by_value = {
                (label.label_type, label.value): label
                for label in session.query(IllumioLabel).all()
            }

            # Prepare all parents first.  The previous implementation opened a
            # SAVEPOINT, flushed, deleted two child collections and flushed
            # again for every workload.  A 40k mock sync consequently issued
            # hundreds of thousands of database round-trips.
            accepted = []
            for raw_record in records:
                try:
                    record = normalize_workload(raw_record)
                    workload = existing.get(record.href)
                    if workload is None:
                        workload = IllumioWorkload(illumio_href=record.href)
                        session.add(workload)
                        existing[record.href] = workload
                        is_new = True
                    else:
                        is_new = False

                    changed = IllumioIngestionService._apply_workload(workload, record)
                    workload.last_seen_at = _utcnow()
                    workload.last_synced_at = _utcnow()
                    accepted.append((record, workload))
                    existing[record.href] = workload
                    if is_new:
                        inserted += 1
                    elif changed:
                        updated += 1
                except Exception:
                    failed += 1

            # One parent flush makes all workload and newly-created label IDs
            # available.  Children are refreshed in set-based deletes and one
            # final insert flush, retaining the original atomic replacement
            # semantics for every accepted workload.
            session.flush()
            workload_ids = [workload.id for _, workload in accepted]
            for batch in _batches(workload_ids):
                session.query(IllumioInterface).filter(
                    IllumioInterface.workload_id.in_(batch)
                ).delete(synchronize_session=False)
                session.query(IllumioWorkloadLabel).filter(
                    IllumioWorkloadLabel.workload_id.in_(batch)
                ).delete(synchronize_session=False)

            for record, workload in accepted:
                for interface in record.interfaces:
                    session.add(IllumioInterface(
                        workload_id=workload.id,
                        interface_name=interface.name,
                        ip_address=interface.address,
                        network_name_or_type=interface.network_name_or_type,
                        raw_json=dict(interface.raw),
                    ))
                for label_record in record.labels:
                    label = IllumioIngestionService._get_or_create_label(
                        session, label_record, label_by_href, label_by_value
                    )
                    session.add(IllumioWorkloadLabel(
                        workload_id=workload.id, label_id=label.id
                    ))
            session.flush()

            run.records_inserted = inserted
            run.records_updated = updated
            run.records_failed = failed
            run.status = "SUCCESS" if not failed else "COMPLETED_WITH_ERRORS"
            run.completed_at = _utcnow()
            session.commit()
        except Exception as exc:
            session.rollback()
            run = session.get(SyncRun, run.id)
            if run is not None:
                run.status = "FAILED"
                run.error_message = str(exc)
                run.completed_at = _utcnow()
                session.commit()
            raise
        finally:
            session.close()

        analyze_tables(
            "illumio_workloads", "illumio_interfaces", "illumio_labels",
            "illumio_workload_labels",
        )
        return {
            "status": "SUCCESS" if not failed else "COMPLETED_WITH_ERRORS",
            "source": source,
            "received": len(records),
            "inserted": inserted,
            "updated": updated,
            "failed": failed,
        }

    @staticmethod
    def _apply_workload(workload: IllumioWorkload, record: CanonicalWorkload) -> bool:
        values = {
            "name": record.name,
            "hostname": record.hostname,
            "online": record.online,
            "connectivity_status": record.connectivity_status,
            "enforcement_mode": record.enforcement_mode,
            "visibility_status": record.visibility_status,
            "policy_sync_status": record.policy_sync_status,
            "ransomware_exposure": record.ransomware_exposure,
            "protection_status": record.protection_status,
            "protection_coverage_score": record.protection_coverage_score,
            "ven_version": record.ven_version,
            "os": record.os,
            "os_release": record.os_release,
            "raw_json": dict(record.raw),
        }
        changed = any(getattr(workload, key) != value for key, value in values.items())
        for key, value in values.items():
            setattr(workload, key, value)
        return changed

    @staticmethod
    def _get_or_create_label(session, record, by_href, by_value):
        label = by_href.get(record.href) if record.href else None
        if label is None:
            label = by_value.get((record.key, record.value))
            if record.href and label is not None and label.illumio_href not in (None, record.href):
                # Distinct source hrefs are distinct label identities even if
                # their current type/value happen to be equal.
                label = None
        if label is None:
            label = IllumioLabel(
                illumio_href=record.href,
                label_type=record.key,
                value=record.value,
                raw_json={"href": record.href, "key": record.key, "value": record.value},
            )
            session.add(label)
            session.flush()
            if record.href:
                by_href[record.href] = label
            by_value[(record.key, record.value)] = label
            return label

        # A stable PCE label href is authoritative.  Keep catalog data current.
        old_key = (label.label_type, label.value)
        if by_value.get(old_key) is label:
            by_value.pop(old_key)
        if record.href and label.illumio_href is None:
            label.illumio_href = record.href
        label.label_type = record.key
        label.value = record.value
        label.raw_json = {"href": record.href, "key": record.key, "value": record.value}
        if record.href:
            by_href[record.href] = label
        by_value[(record.key, record.value)] = label
        return label
