"""
IllumioWriteBackService

Applies approved reconciliation results back to the Illumio PCE
via direct REST API PUT calls — no CSV, no Workloader.

For each approved result it:
  1. Resolves the correct label href from the PCE (or creates it if missing)
  2. PUTs the updated workload with the corrected labels
  3. Marks the reconciliation result as applied or failed
"""

from app.config import settings
from app.repositories.cmdb_repository import ReconciliationRepository


# Maps field_name in reconciliation_results → Illumio label key
_FIELD_TO_LABEL_KEY = {
    # Canonical field names produced by the immutable reconciliation engine.
    "application": "application",
    "role": "role",
    "environment": "environment",
    "location": "location",
    # Legacy results remain actionable/readable where their PCE key was known.
    "role_label": "role",
    "env_label":  "env",
    "loc_label":  "loc",
    "app_label":  "app",
}


class IllumioWriteBackService:

    @staticmethod
    def preview_approved(run_id=None):
        """Return a local-only preflight summary; never contacts the PCE."""
        approved = ReconciliationRepository.get_approved(run_id=run_id)
        eligible = []
        missing_href = 0
        unsupported = 0
        workloads = set()
        for result in approved:
            if not result.illumio_href:
                missing_href += 1
            elif result.field_name not in _FIELD_TO_LABEL_KEY:
                unsupported += 1
            else:
                eligible.append(result)
                workloads.add(result.illumio_href)
        return {
            "approved": len(approved),
            "eligible": len(eligible),
            "workloads": len(workloads),
            "missing_href": missing_href,
            "unsupported": unsupported,
            "real_writes_enabled": (
                settings.ILLUMIO_USE_REAL_CLIENT and settings.ILLUMIO_ALLOW_PCE_WRITEBACK
            ),
        }

    @staticmethod
    def apply_approved(run_id=None, dry_run=False):
        """
        Push all approved reconciliation results to the PCE.

        Args:
            run_id:   Optional — restrict to a specific reconciliation run.
            dry_run:  If True, log what would happen but do not call the API.

        Returns:
            dict: applied, failed, skipped_no_href
        """
        if (
            not (settings.ILLUMIO_USE_REAL_CLIENT and settings.ILLUMIO_ALLOW_PCE_WRITEBACK)
            and not dry_run
        ):
            return {
                "applied": 0,
                "failed": 0,
                "skipped_no_href": 0,
                "note": (
                    "PCE write-back is disabled — set both ILLUMIO_USE_REAL_CLIENT=true "
                    "and ILLUMIO_ALLOW_PCE_WRITEBACK=true, then restart."
                ),
            }

        approved = ReconciliationRepository.get_approved(run_id=run_id)

        if dry_run:
            return {**IllumioWriteBackService.preview_approved(run_id), "dry_run": True}

        from app.services.illumio.real_illumio_client import RealIllumioClient
        client = RealIllumioClient()

        applied = 0
        failed = 0
        skipped = 0

        # Group by workload href so we can batch label changes per workload
        by_href = {}
        for result in approved:
            href = result.illumio_href
            if not href:
                ReconciliationRepository.mark_skipped([result.id])
                skipped += 1
                continue
            by_href.setdefault(href, []).append(result)

        for href, results in by_href.items():
            try:
                if dry_run:
                    for r in results:
                        print(
                            f"[DRY RUN] Would update {href}: "
                            f"{r.field_name} → {r.cmdb_value}"
                        )
                    applied += len(results)
                    continue

                # Fetch current workload from PCE
                workload = client.get_workload(href)

                # The reconciliation row is an immutable record of a prior
                # PCE snapshot.  Never overwrite a label that was changed in
                # PCE after that snapshot was taken; surface it for review.
                IllumioWriteBackService._assert_snapshot_is_current(workload, results)

                # Build updated label list
                updated_labels = IllumioWriteBackService._apply_label_changes(
                    workload.get("labels", []),
                    results,
                    client,
                )

                # PUT updated workload
                client.update_workload_labels(href, updated_labels)

                for r in results:
                    ReconciliationRepository.mark_applied(r.id)
                applied += len(results)

            except Exception as ex:
                error_msg = str(ex)
                for r in results:
                    ReconciliationRepository.mark_applied(r.id, error=error_msg)
                failed += len(results)

        return {
            "applied": applied,
            "failed": failed,
            "skipped_no_href": skipped,
        }

    @staticmethod
    def _apply_label_changes(current_labels, results, client):
        """
        Merge reconciliation changes into the workload's current label list.
        Returns the new label list ready for PUT.
        """
        # current_labels is a list of {"href": "...", "key": "...", "value": "..."}
        # Index by key for easy replacement
        by_key = {lbl.get("key"): lbl for lbl in current_labels}

        requested_values = {}
        for result in results:
            label_key = _FIELD_TO_LABEL_KEY.get(result.field_name)
            if not label_key:
                raise ValueError(f"Result {result.id} has no supported PCE label mapping")

            new_value = result.cmdb_value
            if label_key in requested_values and requested_values[label_key] != new_value:
                raise ValueError(
                    f"Conflicting approved values for {label_key} on one workload"
                )
            requested_values[label_key] = new_value
            if not new_value:
                # Remove this label
                by_key.pop(label_key, None)
                continue

            # Find or create label href
            label_href = client.find_or_create_label(label_key, new_value)
            by_key[label_key] = {"href": label_href}

        return list(by_key.values())

    @staticmethod
    def _assert_snapshot_is_current(workload, results):
        """Reject stale approvals before a PCE PUT can be issued."""
        current = {
            label.get("key"): label.get("value")
            for label in workload.get("labels", [])
            if label.get("key")
        }
        for result in results:
            label_key = _FIELD_TO_LABEL_KEY.get(result.field_name)
            if not label_key:
                raise ValueError(f"Result {result.id} has no supported PCE label mapping")
            expected = (result.illumio_value or "").strip().casefold()
            actual = (current.get(label_key) or "").strip().casefold()
            if actual != expected:
                raise ValueError(
                    f"Stale reconciliation result for {label_key}: PCE now has "
                    f"{current.get(label_key)!r}, expected {result.illumio_value!r}"
                )
