"""Deterministic, snapshot-provenanced CMDB ↔ Illumio reconciliation."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.database import SessionLocal, analyze_tables, engine
from app.models.cmdb_ci import CmdbCi
from app.models.cmdb_import_run import CmdbImportRun
from app.models.illumio.illumio_label import IllumioLabel
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.models.illumio.sync_run import SyncRun
from app.models.reconciliation_result import ReconciliationResult
from app.models.reconciliation_run import ReconciliationRun

_FIELDS = (
    ("cmdb_app", "application"),
    ("cmdb_role", "role"),
    ("cmdb_env", "environment"),
    ("cmdb_loc", "location"),
)
_RESULT_CHUNK = 2_000


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def _normalise_hostname(value):
    value = (value or "").strip().casefold().rstrip(".")
    return value or None


def _is_short(hostname):
    return hostname is not None and "." not in hostname


def _short(hostname):
    return hostname.split(".", 1)[0] if hostname else None


def _values_match(left, right):
    if left is None or right is None:
        return False
    return str(left).strip().casefold() == str(right).strip().casefold()


class ReconciliationService:
    @staticmethod
    def run(progress_callback=None):
        ReconciliationRun.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        run = None
        try:
            cmdb_run = (
                session.query(CmdbImportRun)
                .filter(CmdbImportRun.status == "SUCCESS")
                .order_by(CmdbImportRun.completed_at.desc())
                .first()
            )
            illumio_run = (
                session.query(SyncRun)
                .filter(SyncRun.completed_at.isnot(None))
                .filter(SyncRun.status.in_(("SUCCESS", "COMPLETED_WITH_ERRORS")))
                .order_by(SyncRun.completed_at.desc())
                .first()
            )
            if cmdb_run is None:
                raise ValueError("No successful CMDB snapshot is available for reconciliation.")
            if illumio_run is None:
                raise ValueError("No completed Illumio ingestion is available for reconciliation.")

            run = ReconciliationRun(
                cmdb_import_run_id=cmdb_run.id,
                illumio_sync_run_id=illumio_run.id,
                status="RUNNING",
            )
            session.add(run)
            session.commit()

            cmdb_rows = session.query(
                CmdbCi.id, CmdbCi.hostname, CmdbCi.cmdb_app, CmdbCi.cmdb_role,
                CmdbCi.cmdb_env, CmdbCi.cmdb_loc, CmdbCi.ven_installed,
            ).all()
            illumio_rows = session.query(
                IllumioWorkload.id, IllumioWorkload.hostname, IllumioWorkload.illumio_href,
            ).all()
            labels = defaultdict(dict)
            for row in session.query(
                IllumioWorkloadLabel.workload_id, IllumioLabel.label_type, IllumioLabel.value,
            ).join(IllumioLabel, IllumioLabel.id == IllumioWorkloadLabel.label_id):
                labels[row.workload_id][(row.label_type or "").casefold()] = row.value
            if progress_callback:
                progress_callback(1, 4)

            cmdb_by_exact = defaultdict(list)
            ill_by_exact = defaultdict(list)
            ill_by_short = defaultdict(list)
            for row in cmdb_rows:
                key = _normalise_hostname(row.hostname)
                if key:
                    cmdb_by_exact[key].append(row)
            for row in illumio_rows:
                key = _normalise_hostname(row.hostname)
                if key:
                    ill_by_exact[key].append(row)
                    ill_by_short[_short(key)].append(row)

            outcomes = defaultdict(int)
            results = []
            ambiguous_cmdb_ids, ambiguous_illumio_ids = set(), set()
            candidate_for_cmdb = {}
            cmdb_for_illumio = defaultdict(list)

            # Candidate groups keep duplicates explicit. No dictionary ever
            # chooses an arbitrary workload for a hostname.
            for cmdb in cmdb_rows:
                key = _normalise_hostname(cmdb.hostname)
                if not key:
                    ReconciliationService._add_workload_result(results, run.id, cmdb.hostname, "AMBIGUOUS_MATCH", "CMDB hostname is missing")
                    ambiguous_cmdb_ids.add(cmdb.id)
                    continue
                if len(cmdb_by_exact[key]) > 1:
                    ReconciliationService._add_workload_result(results, run.id, cmdb.hostname, "AMBIGUOUS_MATCH", "Duplicate CMDB hostname")
                    ambiguous_cmdb_ids.add(cmdb.id)
                    for workload in ill_by_exact.get(key, []):
                        ambiguous_illumio_ids.add(workload.id)
                    continue

                candidates = list(ill_by_exact.get(key, []))
                if not candidates:
                    # Short/FQDN fallback is allowed only when one side is a
                    # short hostname, never between differing FQDNs.
                    if _is_short(key):
                        candidates = list(ill_by_short.get(key, []))
                    else:
                        candidates = [row for row in ill_by_short.get(_short(key), []) if _is_short(_normalise_hostname(row.hostname))]
                if len(candidates) == 1:
                    candidate_for_cmdb[cmdb.id] = candidates[0]
                    cmdb_for_illumio[candidates[0].id].append(cmdb)
                elif len(candidates) > 1:
                    ReconciliationService._add_workload_result(results, run.id, cmdb.hostname, "AMBIGUOUS_MATCH", "Multiple Illumio candidates")
                    ambiguous_cmdb_ids.add(cmdb.id)
                    ambiguous_illumio_ids.update(row.id for row in candidates)
                else:
                    ReconciliationService._add_workload_result(results, run.id, cmdb.hostname, "MISSING_IN_ILLUMIO", None, cmdb_ven=cmdb.ven_installed)
                    outcomes["missing_in_illumio"] += 1

            for workload_id, cmdb_candidates in cmdb_for_illumio.items():
                if len(cmdb_candidates) > 1:
                    ambiguous_illumio_ids.add(workload_id)
                    for cmdb in cmdb_candidates:
                        if cmdb.id not in ambiguous_cmdb_ids:
                            ReconciliationService._add_workload_result(results, run.id, cmdb.hostname, "AMBIGUOUS_MATCH", "Multiple CMDB candidates")
                            ambiguous_cmdb_ids.add(cmdb.id)

            if progress_callback:
                progress_callback(2, 4)

            matched_illumio_ids = set()
            for cmdb in cmdb_rows:
                workload = candidate_for_cmdb.get(cmdb.id)
                if workload is None or cmdb.id in ambiguous_cmdb_ids or workload.id in ambiguous_illumio_ids:
                    continue
                matched_illumio_ids.add(workload.id)
                workload_has_issue = False
                workload_labels = labels.get(workload.id, {})
                for cmdb_column, label_key in _FIELDS:
                    expected = getattr(cmdb, cmdb_column)
                    current = workload_labels.get(label_key)
                    if expected is None or not str(expected).strip():
                        status = "NO_EXPECTED_VALUE"
                        outcomes["no_expected_value"] += 1
                    elif current is None or not str(current).strip():
                        status = "LABEL_MISSING"
                        outcomes["label_missing"] += 1
                    elif _values_match(expected, current):
                        continue
                    else:
                        status = "LABEL_MISMATCH"
                        outcomes["label_mismatches"] += 1
                    workload_has_issue = True
                    results.append(ReconciliationResult(
                        run_id=run.id, hostname=cmdb.hostname, field_name=label_key,
                        illumio_value=current, cmdb_value=expected, status=status,
                        resolution_action="pending", illumio_href=workload.illumio_href,
                    ))
                if not workload_has_issue:
                    outcomes["matched_workloads"] += 1

            for workload in illumio_rows:
                if workload.id in matched_illumio_ids:
                    continue
                if workload.id in ambiguous_illumio_ids:
                    ReconciliationService._add_workload_result(results, run.id, workload.hostname, "AMBIGUOUS_MATCH", "Ambiguous CMDB/Illumio candidate group", illumio_href=workload.illumio_href)
                    continue
                # A workload only considered by an ambiguous CMDB group is not
                # an orphan; it is a review condition.
                ReconciliationService._add_workload_result(results, run.id, workload.hostname, "ORPHANED_IN_ILLUMIO", None, illumio_href=workload.illumio_href)
                outcomes["orphaned_in_illumio"] += 1

            outcomes["ambiguous_matches"] = sum(1 for result in results if result.status == "AMBIGUOUS_MATCH")
            if progress_callback:
                progress_callback(3, 4)
            for offset in range(0, len(results), _RESULT_CHUNK):
                session.bulk_save_objects(results[offset:offset + _RESULT_CHUNK])
                session.commit()

            run = session.get(ReconciliationRun, run.id)
            for key in ("matched_workloads", "label_mismatches", "label_missing", "no_expected_value", "missing_in_illumio", "orphaned_in_illumio", "ambiguous_matches"):
                setattr(run, key, outcomes[key])
            run.actionable_results = len(results)
            run.status = "SUCCESS"
            run.completed_at = _utcnow()
            session.commit()
            if progress_callback:
                progress_callback(4, 4)
            return {
                "run_id": run.id, "cmdb_import_run_id": cmdb_run.id, "illumio_sync_run_id": illumio_run.id,
                "total_cmdb": len(cmdb_rows), "total_illumio": len(illumio_rows), "total_results": len(results),
                **{key: outcomes[key] for key in outcomes},
            }
        except Exception as exc:
            session.rollback()
            if run is not None:
                failed = session.get(ReconciliationRun, run.id)
                if failed:
                    failed.status = "FAILED"
                    failed.error_message = str(exc)
                    failed.completed_at = _utcnow()
                    session.commit()
            raise
        finally:
            session.close()
            analyze_tables("reconciliation_results")

    @staticmethod
    def _add_workload_result(results, run_id, hostname, status, detail, illumio_href=None, cmdb_ven=None):
        results.append(ReconciliationResult(
            run_id=run_id, hostname=hostname, illumio_href=illumio_href,
            field_name="workload", illumio_value=detail,
            cmdb_value=("VEN installed" if cmdb_ven is True else "VEN not installed" if cmdb_ven is False else None),
            status=status, resolution_action="pending",
        ))
