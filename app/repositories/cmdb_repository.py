import json

from sqlalchemy import String, cast, or_

from app.database import SessionLocal, engine
from app.models.cmdb_ci import CmdbCi
from app.models.cmdb_import_run import CmdbImportRun
from app.models.illumio.ingestion_source import IngestionSource
from app.models.illumio.sync_run import SyncRun
from app.models.reconciliation_result import ReconciliationResult
from app.models.reconciliation_run import ReconciliationRun
from app.services.performance import timed


_CHUNK = 500

# Columns projected for the table list view — excludes large/unused fields
# (extra_fields JSONB, description Text, distinguished_name, etc.)
_CMDB_LIST_COLS = [
    CmdbCi.id,
    CmdbCi.hostname,
    CmdbCi.cmdb_app,
    CmdbCi.cmdb_role,
    CmdbCi.cmdb_env,
    CmdbCi.cmdb_loc,
    CmdbCi.region,
    CmdbCi.ven_installed,
]

# The quick lookup deliberately covers the normal CMDB identity, label, and
# inventory fields. Unknown imported columns remain searchable through
# extra_fields so a source-specific CI identifier is not lost to the browser.
_CMDB_QUICK_SEARCH_COLUMNS = (
    CmdbCi.hostname,
    CmdbCi.cmdb_app,
    CmdbCi.cmdb_role,
    CmdbCi.cmdb_env,
    CmdbCi.cmdb_loc,
    CmdbCi.region,
    CmdbCi.district,
    CmdbCi.wave,
    CmdbCi.description,
    CmdbCi.public_ip,
    CmdbCi.distinguished_name,
    CmdbCi.ip_with_default_gw,
    CmdbCi.default_gw,
    CmdbCi.data_center,
    CmdbCi.data_center_zone,
    CmdbCi.service_provider,
    CmdbCi.cloud_instance_id,
    CmdbCi.os,
    CmdbCi.os_detail,
    CmdbCi.parent_application,
    CmdbCi.parent_sys_class_name,
    CmdbCi.child_sys_class_name,
)
_CMDB_BULK_CHUNK_SIZE = 500
_CMDB_BULK_FALLBACK_CHUNK_SIZE = 250

# Columns projected for the reconciliation table list view
_RECON_LIST_COLS = [
    ReconciliationResult.id,
    ReconciliationResult.hostname,
    ReconciliationResult.illumio_href,
    ReconciliationResult.field_name,
    ReconciliationResult.illumio_value,
    ReconciliationResult.cmdb_value,
    ReconciliationResult.status,
    ReconciliationResult.resolution_action,
    ReconciliationResult.run_id,
]


def _apply_cmdb_filters(q, search_text, app, region):
    if search_text:
        pattern = f"%{search_text}%"
        q = q.filter(or_(
            *(column.ilike(pattern) for column in _CMDB_QUICK_SEARCH_COLUMNS),
            cast(CmdbCi.extra_fields, String).ilike(pattern),
        ))
    if app:
        q = q.filter(CmdbCi.cmdb_app.ilike(f"%{app}%"))
    if region:
        q = q.filter(CmdbCi.region.ilike(f"%{region}%"))
    return q


class CmdbRepository:

    @staticmethod
    def latest_import_metadata():
        """Latest successful current-domain CMDB snapshot provenance."""
        CmdbImportRun.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        try:
            with timed("cmdb.repository.source_metadata"):
                return (
                    session.query(CmdbImportRun)
                    .filter(CmdbImportRun.status == "SUCCESS")
                    .order_by(CmdbImportRun.completed_at.desc())
                    .first()
                )
        finally:
            session.close()

    @staticmethod
    def search(
        search_text=None,
        app=None,
        region=None,
        limit=500,
        offset=0,
        hostname=None,
        sort_by="hostname",
        sort_direction="asc",
    ):
        # hostname is retained as a backward-compatible keyword for callers
        # from before CMDB lookup became cross-field.
        search_text = search_text if search_text is not None else hostname
        session = SessionLocal()
        try:
            with timed("cmdb.repository.page"):
                q = session.query(*_CMDB_LIST_COLS)
                q = _apply_cmdb_filters(q, search_text, app, region)
                sort_columns = {
                    "hostname": CmdbCi.hostname,
                    "application": CmdbCi.cmdb_app,
                    "role": CmdbCi.cmdb_role,
                    "environment": CmdbCi.cmdb_env,
                    "location": CmdbCi.cmdb_loc,
                    "region": CmdbCi.region,
                    "ven": CmdbCi.ven_installed,
                }
                order_column = sort_columns.get(sort_by, CmdbCi.hostname)
                order_by = order_column.desc() if sort_direction == "desc" else order_column.asc()
                return (
                    q.order_by(order_by, CmdbCi.id.asc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
        finally:
            session.close()

    @staticmethod
    def count(search_text=None, app=None, region=None, hostname=None):
        search_text = search_text if search_text is not None else hostname
        session = SessionLocal()
        try:
            with timed("cmdb.repository.count"):
                q = session.query(CmdbCi.id)
                q = _apply_cmdb_filters(q, search_text, app, region)
                return q.count()
        finally:
            session.close()

    @staticmethod
    def total_count():
        session = SessionLocal()
        try:
            with timed("cmdb.repository.total_count"):
                return session.query(CmdbCi.id).count()
        finally:
            session.close()

    @staticmethod
    def get_by_hostname(hostname):
        session = SessionLocal()
        try:
            return (
                session.query(CmdbCi)
                .filter(CmdbCi.hostname == hostname)
                .first()
            )
        finally:
            session.close()

    @staticmethod
    def bulk_search(terms, app=None, region=None):
        """Find CMDB records for pasted identifiers across searchable fields.

        Terms are queried in bounded batches. Records are deduplicated by
        database ID, never by hostname, so duplicate CMDB rows remain visible.
        """
        clean = list(dict.fromkeys(
            term.strip() for term in terms if term and term.strip()
        ))
        if not clean:
            return {"found": [], "missing": []}

        session = SessionLocal()
        try:
            found_ids = set()
            matched_terms = set()
            # Exact matching handles the common pasted-hostname/label case in
            # a small number of set-based queries before considering slower
            # partial lookup across source-specific inventory fields.
            for start in range(0, len(clean), _CMDB_BULK_CHUNK_SIZE):
                term_chunk = clean[start:start + _CMDB_BULK_CHUNK_SIZE]
                query = session.query(CmdbCi).filter(or_(*(
                    column.in_(term_chunk) for column in _CMDB_QUICK_SEARCH_COLUMNS
                )))
                query = _apply_cmdb_filters(query, None, app, region)
                for record in query.all():
                    found_ids.add(record.id)
                    values = _cmdb_search_values(record)
                    for term in term_chunk:
                        if any(term.casefold() == value.casefold() for value in values):
                            matched_terms.add(term)

            unmatched = [term for term in clean if term not in matched_terms]
            for start in range(0, len(unmatched), _CMDB_BULK_FALLBACK_CHUNK_SIZE):
                term_chunk = unmatched[start:start + _CMDB_BULK_FALLBACK_CHUNK_SIZE]
                conditions = []
                for term in term_chunk:
                    pattern = f"%{term}%"
                    conditions.extend(column.ilike(pattern) for column in _CMDB_QUICK_SEARCH_COLUMNS)
                    conditions.append(cast(CmdbCi.extra_fields, String).ilike(pattern))
                query = session.query(CmdbCi).filter(or_(*conditions))
                query = _apply_cmdb_filters(query, None, app, region)
                for record in query.all():
                    found_ids.add(record.id)
                    values = _cmdb_search_values(record)
                    for term in term_chunk:
                        if any(term.casefold() in value.casefold() for value in values):
                            matched_terms.add(term)

            found = []
            for start in range(0, len(found_ids), _CMDB_BULK_CHUNK_SIZE):
                id_chunk = list(found_ids)[start:start + _CMDB_BULK_CHUNK_SIZE]
                found.extend(
                    session.query(CmdbCi)
                    .filter(CmdbCi.id.in_(id_chunk))
                    .order_by(CmdbCi.hostname, CmdbCi.id)
                    .all()
                )
            found.sort(key=lambda record: ((record.hostname or "").casefold(), record.id))
            return {"found": found, "missing": [term for term in clean if term not in matched_terms]}
        finally:
            session.close()

    @staticmethod
    def truncate():
        """Remove all rows — called before a fresh import."""
        session = SessionLocal()
        try:
            session.query(CmdbCi).delete()
            session.commit()
        finally:
            session.close()


def _cmdb_search_values(record):
    values = [getattr(record, column.key) for column in _CMDB_QUICK_SEARCH_COLUMNS]
    if record.extra_fields:
        values.append(json.dumps(record.extra_fields, sort_keys=True, default=str))
    return [str(value) for value in values if value is not None]


def _apply_recon_filters(q, status, field_name, resolution_action, hostname, run_id):
    if status and status != "All":
        q = q.filter(ReconciliationResult.status == status)
    if field_name and field_name != "All":
        q = q.filter(ReconciliationResult.field_name == field_name)
    if resolution_action and resolution_action != "All":
        q = q.filter(ReconciliationResult.resolution_action == resolution_action)
    if hostname:
        q = q.filter(ReconciliationResult.hostname.ilike(f"%{hostname}%"))
    if run_id is not None:
        q = q.filter(ReconciliationResult.run_id == run_id)
    return q


class ReconciliationRepository:

    _APPROVABLE_STATUSES = ("LABEL_MISMATCH", "LABEL_MISSING", "mismatch", "label_missing")

    @staticmethod
    def latest_completed_run():
        ReconciliationRun.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        try:
            with timed("reconciliation.repository.latest_run"):
                return (
                    session.query(ReconciliationRun)
                    .filter(ReconciliationRun.status == "SUCCESS")
                    .order_by(ReconciliationRun.completed_at.desc())
                    .first()
                )
        finally:
            session.close()

    @staticmethod
    def get_run_context(run_id):
        IngestionSource.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        try:
            with timed("reconciliation.repository.run_context"):
                return (
                    session.query(ReconciliationRun, CmdbImportRun, SyncRun, IngestionSource)
                    .outerjoin(CmdbImportRun, CmdbImportRun.id == ReconciliationRun.cmdb_import_run_id)
                    .outerjoin(SyncRun, SyncRun.id == ReconciliationRun.illumio_sync_run_id)
                    .outerjoin(IngestionSource, IngestionSource.sync_run_id == SyncRun.id)
                    .filter(ReconciliationRun.id == run_id)
                    .first()
                )
        finally:
            session.close()

    @staticmethod
    def search(
        status=None,
        field_name=None,
        resolution_action=None,
        hostname=None,
        run_id=None,
        limit=500,
        offset=0,
        sort_by="hostname",
        sort_direction="asc",
    ):
        session = SessionLocal()
        try:
            with timed("reconciliation.repository.page"):
                q = session.query(*_RECON_LIST_COLS)
                q = _apply_recon_filters(
                    q, status, field_name, resolution_action, hostname, run_id
                )
                sort_columns = {
                    "hostname": ReconciliationResult.hostname,
                    "field": ReconciliationResult.field_name,
                    "status": ReconciliationResult.status,
                    "action": ReconciliationResult.resolution_action,
                }
                order_column = sort_columns.get(sort_by, ReconciliationResult.hostname)
                order_by = order_column.desc() if sort_direction == "desc" else order_column.asc()
                return (
                    q.order_by(order_by, ReconciliationResult.id.asc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
        finally:
            session.close()

    @staticmethod
    def count(
        status=None,
        field_name=None,
        resolution_action=None,
        hostname=None,
        run_id=None,
    ):
        session = SessionLocal()
        try:
            with timed("reconciliation.repository.count"):
                q = session.query(ReconciliationResult.id)
                q = _apply_recon_filters(
                    q, status, field_name, resolution_action, hostname, run_id
                )
                return q.count()
        finally:
            session.close()

    @staticmethod
    def get_approved(run_id=None):
        """Return all results approved but not yet applied."""
        session = SessionLocal()
        try:
            q = session.query(ReconciliationResult).filter(
                ReconciliationResult.resolution_action == "approved",
                ReconciliationResult.status.in_(ReconciliationRepository._APPROVABLE_STATUSES),
            )
            if run_id is not None:
                q = q.filter(ReconciliationResult.run_id == run_id)
            return q.all()
        finally:
            session.close()

    @staticmethod
    def mark_approved(ids):
        session = SessionLocal()
        try:
            session.query(ReconciliationResult).filter(
                ReconciliationResult.id.in_(ids),
                ReconciliationResult.status.in_(ReconciliationRepository._APPROVABLE_STATUSES),
            ).update(
                {"resolution_action": "approved"},
                synchronize_session=False,
            )
            session.commit()
        finally:
            session.close()

    @staticmethod
    def mark_skipped(ids):
        session = SessionLocal()
        try:
            session.query(ReconciliationResult).filter(
                ReconciliationResult.id.in_(ids)
            ).update(
                {"resolution_action": "skipped", "resolved": True},
                synchronize_session=False,
            )
            session.commit()
        finally:
            session.close()

    @staticmethod
    def mark_applied(id_, error=None):
        from datetime import datetime
        session = SessionLocal()
        try:
            r = session.query(ReconciliationResult).get(id_)
            if r:
                r.resolution_action = "applied" if not error else "failed"
                r.resolved = not bool(error)
                r.resolved_at = datetime.utcnow()
                r.error_message = error
                session.commit()
        finally:
            session.close()

    @staticmethod
    def clear_run(run_id):
        session = SessionLocal()
        try:
            session.query(ReconciliationResult).filter(
                ReconciliationResult.run_id == run_id
            ).delete()
            session.commit()
        finally:
            session.close()

    @staticmethod
    def latest_run_id():
        session = SessionLocal()
        try:
            from sqlalchemy import func
            result = session.query(
                func.max(ReconciliationResult.run_id)
            ).scalar()
            return result or 0
        finally:
            session.close()
