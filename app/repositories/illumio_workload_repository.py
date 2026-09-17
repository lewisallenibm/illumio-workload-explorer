from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal, engine

from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_label import IllumioLabel
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.models.illumio.ingestion_source import IngestionSource
from app.models.illumio.sync_run import SyncRun
from app.services.performance import timed

# PostgreSQL has a limit on bind parameters; chunk bulk lists at this size
_BULK_CHUNK_SIZE = 500
# Each partial lookup expands into six OR predicates. Keep the batch below
# SQLite's expression-depth limit too, so browser-path tests exercise the same
# bounded query strategy used with PostgreSQL.
_FALLBACK_CHUNK_SIZE = 150

# Columns loaded for the table list view — excludes raw_json which is large
# and only needed when a row is selected for the details panel.
_LIST_COLS = [
    IllumioWorkload.id,
    IllumioWorkload.illumio_href,
    IllumioWorkload.hostname,
    IllumioWorkload.name,
    IllumioWorkload.online,
    IllumioWorkload.connectivity_status,
    IllumioWorkload.enforcement_mode,
    IllumioWorkload.visibility_status,
    IllumioWorkload.policy_sync_status,
    IllumioWorkload.protection_status,
    IllumioWorkload.protection_coverage_score,
    IllumioWorkload.ven_version,
    IllumioWorkload.os,
    IllumioWorkload.os_release,
]


class IllumioWorkloadRepository:

    @staticmethod
    def _build_filter(query, search_text, online, enforcement, session):
        """Apply filters to a query. session is needed for lookup subqueries."""

        if search_text:
            ip_match = select(IllumioInterface.workload_id).where(
                IllumioInterface.ip_address.ilike(f"%{search_text}%")
            )
            label_match = (
                select(IllumioWorkloadLabel.workload_id)
                .join(IllumioLabel, IllumioLabel.id == IllumioWorkloadLabel.label_id)
                .where(or_(
                    IllumioLabel.value.ilike(f"%{search_text}%"),
                    IllumioLabel.label_type.ilike(f"%{search_text}%"),
                ))
            )
            query = query.filter(
                or_(
                    IllumioWorkload.hostname.ilike(f"%{search_text}%"),
                    IllumioWorkload.name.ilike(f"%{search_text}%"),
                    IllumioWorkload.illumio_href.ilike(f"%{search_text}%"),
                    IllumioWorkload.id.in_(ip_match),
                    IllumioWorkload.id.in_(label_match),
                )
            )

        if online is not None:
            query = query.filter(IllumioWorkload.online == online)

        if enforcement:
            query = query.filter(IllumioWorkload.enforcement_mode == enforcement)

        return query

    @staticmethod
    def search(
        search_text=None,
        online=None,
        enforcement=None,
        limit=500,
        offset=0,
        sort_by="hostname",
        sort_direction="asc",
    ):
        """
        Return lightweight row objects for the table — no raw_json loaded.
        Rows behave like ORM objects for attribute access on the listed cols.
        """
        session = SessionLocal()
        try:
            with timed("workloads.repository.page"):
                query = session.query(*_LIST_COLS)
                query = IllumioWorkloadRepository._build_filter(
                    query, search_text, online, enforcement, session
                )
                sort_columns = {
                    "hostname": IllumioWorkload.hostname,
                    "online": IllumioWorkload.online,
                    "enforcement": IllumioWorkload.enforcement_mode,
                    "ven": IllumioWorkload.ven_version,
                    "os": IllumioWorkload.os,
                }
                order_column = sort_columns.get(sort_by, IllumioWorkload.hostname)
                order_by = order_column.desc() if sort_direction == "desc" else order_column.asc()
                return (
                    query
                    .order_by(order_by, IllumioWorkload.id.asc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
        finally:
            session.close()

    @staticmethod
    def count(
        search_text=None,
        online=None,
        enforcement=None,
    ):
        session = SessionLocal()
        try:
            with timed("workloads.repository.count"):
                query = session.query(IllumioWorkload.id)
                query = IllumioWorkloadRepository._build_filter(
                    query, search_text, online, enforcement, session
                )
                return query.count()
        finally:
            session.close()

    @staticmethod
    def total_count():
        session = SessionLocal()
        try:
            return session.query(IllumioWorkload.id).count()
        finally:
            session.close()

    @staticmethod
    def get_by_hostname(hostname):
        """Load the first workload matching hostname with labels and interfaces."""
        session = SessionLocal()
        try:
            return (
                session.query(IllumioWorkload)
                .options(
                    selectinload(IllumioWorkload.interfaces),
                    selectinload(IllumioWorkload.labels).selectinload(
                        IllumioWorkloadLabel.label
                    ),
                )
                .filter(IllumioWorkload.hostname == hostname)
                .first()
            )
        finally:
            session.close()

    @staticmethod
    def get_by_id(workload_id):
        """Load a real ORM workload with its labels and interfaces preloaded."""
        session = SessionLocal()
        try:
            with timed("workloads.repository.detail"):
                return (
                    session.query(IllumioWorkload)
                    .options(
                        selectinload(IllumioWorkload.interfaces),
                        selectinload(IllumioWorkload.labels).selectinload(
                            IllumioWorkloadLabel.label
                        ),
                    )
                    .filter(IllumioWorkload.id == workload_id)
                    .first()
                )
        finally:
            session.close()

    @staticmethod
    def latest_ingestion_metadata():
        """Return compact provenance for the most recently completed ingestion."""
        IngestionSource.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        try:
            with timed("workloads.repository.source_metadata"):
                return (
                    session.query(IngestionSource, SyncRun)
                    .join(SyncRun, SyncRun.id == IngestionSource.sync_run_id)
                    .filter(SyncRun.completed_at.isnot(None))
                    .order_by(SyncRun.completed_at.desc())
                    .first()
                )
        finally:
            session.close()

    @staticmethod
    def bulk_search(
        terms,
        online=None,
        enforcement=None,
    ):
        """
        Search for a large list of workload identifiers and values.

        Each term is matched against hostname, name, Illumio href, interface
        IP, and label type/value. Any unmatched term falls back to a bounded
        case-insensitive partial match across the same fields.

        Returns a dict:
            {
                "found":   [IllumioWorkload, ...],   # deduplicated
                "missing": ["term1", "term2", ...],  # nothing matched
            }

        Handles thousands of terms safely by chunking SQL IN clauses to
        avoid PostgreSQL's bind-parameter limit.
        """

        if not terms:
            return {"found": [], "missing": []}

        session = SessionLocal()

        try:

            # Normalise: strip whitespace, drop blanks, deduplicate
            clean = list(
                dict.fromkeys(
                    t.strip() for t in terms if t.strip()
                )
            )

            found_ids = set()
            matched_terms = set()

            # --- Phase 1: exact match on indexed identity values ------------
            for chunk_start in range(0, len(clean), _BULK_CHUNK_SIZE):

                chunk = clean[chunk_start: chunk_start + _BULK_CHUNK_SIZE]

                # Workloads whose hostname, name, or href exactly matches a term.
                hostname_rows = (
                    session.query(IllumioWorkload)
                    .filter(or_(
                        IllumioWorkload.hostname.in_(chunk),
                        IllumioWorkload.name.in_(chunk),
                        IllumioWorkload.illumio_href.in_(chunk),
                    ))
                    .all()
                )

                for w in hostname_rows:
                    found_ids.add(w.id)
                    for value in (w.hostname, w.name, w.illumio_href):
                        if value in chunk:
                            matched_terms.add(value)

                # Workload IDs reachable via an exact IP match
                ip_rows = (
                    session.query(IllumioInterface)
                    .filter(
                        IllumioInterface.ip_address.in_(chunk)
                    )
                    .all()
                )

                for iface in ip_rows:
                    found_ids.add(iface.workload_id)
                    if iface.ip_address in chunk:
                        matched_terms.add(iface.ip_address)

                label_rows = (
                    session.query(
                        IllumioWorkloadLabel.workload_id,
                        IllumioLabel.label_type,
                        IllumioLabel.value,
                    )
                    .join(IllumioLabel, IllumioLabel.id == IllumioWorkloadLabel.label_id)
                    .filter(or_(
                        IllumioLabel.label_type.in_(chunk),
                        IllumioLabel.value.in_(chunk),
                    ))
                    .all()
                )
                for label in label_rows:
                    found_ids.add(label.workload_id)
                    for value in (label.label_type, label.value):
                        if value in chunk:
                            matched_terms.add(value)

            # --- Phase 2: bounded, set-based ILIKE fallback ---------------
            unmatched = [t for t in clean if t not in matched_terms]

            for start in range(0, len(unmatched), _FALLBACK_CHUNK_SIZE):
                terms_chunk = unmatched[start:start + _FALLBACK_CHUNK_SIZE]
                conditions = []
                for term in terms_chunk:
                    conditions.extend((
                        IllumioWorkload.hostname.ilike(f"%{term}%"),
                        IllumioWorkload.name.ilike(f"%{term}%"),
                        IllumioWorkload.illumio_href.ilike(f"%{term}%"),
                        IllumioInterface.ip_address.ilike(f"%{term}%"),
                        IllumioLabel.label_type.ilike(f"%{term}%"),
                        IllumioLabel.value.ilike(f"%{term}%"),
                    ))
                rows = (
                    session.query(
                        IllumioWorkload.id,
                        IllumioWorkload.hostname,
                        IllumioWorkload.name,
                        IllumioWorkload.illumio_href,
                        IllumioInterface.ip_address,
                        IllumioLabel.label_type,
                        IllumioLabel.value.label("label_value"),
                    )
                    .outerjoin(
                        IllumioInterface,
                        IllumioInterface.workload_id == IllumioWorkload.id,
                    )
                    .outerjoin(
                        IllumioWorkloadLabel,
                        IllumioWorkloadLabel.workload_id == IllumioWorkload.id,
                    )
                    .outerjoin(
                        IllumioLabel,
                        IllumioLabel.id == IllumioWorkloadLabel.label_id,
                    )
                    .filter(or_(*conditions))
                    .all()
                )
                for row in rows:
                    values = [
                        (row.hostname or "").casefold(),
                        (row.name or "").casefold(),
                        (row.illumio_href or "").casefold(),
                        (row.ip_address or "").casefold(),
                        (row.label_type or "").casefold(),
                        (row.label_value or "").casefold(),
                    ]
                    for term in terms_chunk:
                        if any(term.casefold() in value for value in values):
                            matched_terms.add(term)
                            found_ids.add(row.id)

            # --- Fetch full workload objects for all matched IDs -----------
            found = []

            for chunk_start in range(
                0, len(found_ids), _BULK_CHUNK_SIZE
            ):

                chunk = list(found_ids)[
                    chunk_start: chunk_start + _BULK_CHUNK_SIZE
                ]

                rows = (
                    session.query(IllumioWorkload)
                    .filter(IllumioWorkload.id.in_(chunk))
                )

                if online is not None:
                    rows = rows.filter(
                        IllumioWorkload.online == online
                    )

                if enforcement:
                    rows = rows.filter(
                        IllumioWorkload.enforcement_mode == enforcement
                    )

                found.extend(
                    rows.order_by(IllumioWorkload.hostname).all()
                )

            found.sort(key=lambda workload: ((workload.hostname or "").casefold(), workload.id))

            missing = [t for t in clean if t not in matched_terms]

            return {
                "found": found,
                "missing": missing,
            }

        finally:

            session.close()
