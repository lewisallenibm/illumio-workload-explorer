"""Scheduled export/report foundation shared by web and future worker hosts.

The service is intentionally safe-by-default:
* automations are created disabled;
* the default delivery channel is a local outbox, not email or Box;
* external delivery requires both a configured channel and an explicit runtime
  ``AUTOMATION_ENABLE_EXTERNAL_DELIVERY=true`` gate.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

import requests
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models.automation import (
    Automation,
    AutomationRun,
    DeliveryRecipient,
    DeliverySubscription,
)
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.models.reconciliation_run import ReconciliationRun


MAX_RECIPIENTS = 10
TASK_WORKLOAD_EXPORT = "WORKLOAD_EXPORT"
TASK_COMPATIBILITY_REPORT = "COMPATIBILITY_REPORT"
CHANNEL_LOCAL_OUTBOX = "LOCAL_OUTBOX"
CHANNEL_SMTP = "SMTP"
CHANNEL_BOX = "BOX"
VALID_CHANNELS = {CHANNEL_LOCAL_OUTBOX, CHANNEL_SMTP, CHANNEL_BOX}
VALID_SCHEDULES = {"DAILY", "WEEKLY"}
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_DEFAULT_AUTOMATIONS = (
    {
        "task_type": TASK_WORKLOAD_EXPORT,
        "display_name": "Workload Export",
        "schedule_type": "DAILY",
        "weekday": None,
        "run_time_utc": "13:00",
    },
    {
        "task_type": TASK_COMPATIBILITY_REPORT,
        "display_name": "Compatibility Report",
        "schedule_type": "WEEKLY",
        "weekday": 0,
        "run_time_utc": "13:00",
    },
)


class AutomationConfigurationError(ValueError):
    """A clear operator-facing configuration issue; never expose credentials."""


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _validate_time(value: str) -> str:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value or ""):
        raise AutomationConfigurationError("Time must use 24-hour HH:MM format.")
    return value


class AutomationService:
    """Persist schedules, create artifacts, and safely dispatch configured deliveries."""

    def __init__(self, session_factory=SessionLocal, outbox_dir: Path | None = None):
        self._session_factory = session_factory
        configured_outbox = os.getenv("AUTOMATION_OUTBOX_DIR", "var/automation-outbox")
        self._outbox_dir = Path(outbox_dir or configured_outbox)

    def bootstrap_defaults(self) -> list[Automation]:
        with self._session_factory() as session:
            for values in _DEFAULT_AUTOMATIONS:
                automation = session.query(Automation).filter_by(task_type=values["task_type"]).one_or_none()
                if automation is None:
                    session.add(Automation(**values, enabled=False, delivery_channel=CHANNEL_LOCAL_OUTBOX))
                else:
                    automation.display_name = values["display_name"]
            session.commit()
            return session.query(Automation).order_by(Automation.id).all()

    def list_automations(self) -> list[Automation]:
        self.bootstrap_defaults()
        with self._session_factory() as session:
            return session.query(Automation).order_by(Automation.id).all()

    def list_recipients(self) -> list[DeliveryRecipient]:
        with self._session_factory() as session:
            return session.query(DeliveryRecipient).order_by(DeliveryRecipient.slot).all()

    def list_subscriptions(self) -> dict[tuple[int, int], DeliverySubscription]:
        with self._session_factory() as session:
            rows = session.query(DeliverySubscription).all()
            return {(row.automation_id, row.recipient_id): row for row in rows}

    def save_recipient(self, *, slot: int, display_name: str, email: str, enabled: bool) -> DeliveryRecipient:
        if not 1 <= slot <= MAX_RECIPIENTS:
            raise AutomationConfigurationError(f"Recipient slot must be between 1 and {MAX_RECIPIENTS}.")
        email = email.strip()
        if not _EMAIL.fullmatch(email):
            raise AutomationConfigurationError("Enter a valid recipient email address.")
        display_name = display_name.strip()
        if not display_name:
            raise AutomationConfigurationError("Recipient name is required.")
        with self._session_factory() as session:
            recipient = session.query(DeliveryRecipient).filter_by(slot=slot).one_or_none()
            if recipient is None:
                recipient = DeliveryRecipient(slot=slot, display_name=display_name, email=email, enabled=enabled)
                session.add(recipient)
            else:
                recipient.display_name = display_name
                recipient.email = email
                recipient.enabled = enabled
            session.commit()
            session.refresh(recipient)
            return recipient

    def delete_recipient(self, *, slot: int) -> None:
        """Remove a pilot recipient and their task-specific delivery choices."""
        with self._session_factory() as session:
            recipient = session.query(DeliveryRecipient).filter_by(slot=slot).one_or_none()
            if recipient is None:
                raise AutomationConfigurationError("Recipient was not found.")
            session.query(DeliverySubscription).filter_by(recipient_id=recipient.id).delete()
            session.delete(recipient)
            session.commit()

    def update_automation(
        self,
        automation_id: int,
        *,
        enabled: bool,
        schedule_type: str,
        weekday: int | None,
        run_time_utc: str,
        delivery_channels: Iterable[str] | str,
        box_folder_id: str | None,
    ) -> Automation:
        schedule_type = schedule_type.upper()
        delivery_channels = self._normalize_delivery_channels(delivery_channels)
        if schedule_type not in VALID_SCHEDULES:
            raise AutomationConfigurationError("Schedule must be DAILY or WEEKLY.")
        if schedule_type == "WEEKLY" and weekday not in range(7):
            raise AutomationConfigurationError("Weekly schedules require a weekday from 0 (Monday) through 6.")
        with self._session_factory() as session:
            automation = session.get(Automation, automation_id)
            if automation is None:
                raise AutomationConfigurationError("Automation was not found.")
            automation.enabled = enabled
            automation.schedule_type = schedule_type
            automation.weekday = weekday if schedule_type == "WEEKLY" else None
            automation.run_time_utc = _validate_time(run_time_utc)
            automation.delivery_channel = ",".join(delivery_channels)
            automation.box_folder_id = (box_folder_id or "").strip() or None
            session.commit()
            session.refresh(automation)
            return automation

    @staticmethod
    def _normalize_delivery_channels(value: Iterable[str] | str) -> tuple[str, ...]:
        values = [value] if isinstance(value, str) else list(value)
        channels = tuple(dict.fromkeys(channel.strip().upper() for value in values for channel in value.split(",") if channel.strip()))
        if not channels:
            raise AutomationConfigurationError("Select at least one delivery channel.")
        unsupported = set(channels) - VALID_CHANNELS
        if unsupported:
            raise AutomationConfigurationError("Unsupported delivery channel.")
        return channels

    def set_subscription(
        self,
        *,
        automation_id: int,
        recipient_id: int,
        enabled: bool,
        schedule_type: str = "INHERIT",
        weekday: int | None = None,
        run_time_utc: str | None = None,
    ) -> DeliverySubscription:
        schedule_type = schedule_type.upper()
        if schedule_type not in {"INHERIT", *VALID_SCHEDULES}:
            raise AutomationConfigurationError("Recipient schedule must be INHERIT, DAILY, or WEEKLY.")
        if schedule_type == "WEEKLY" and weekday not in range(7):
            raise AutomationConfigurationError("Weekly recipient schedules require a weekday from 0 through 6.")
        if run_time_utc is not None:
            run_time_utc = _validate_time(run_time_utc)
        with self._session_factory() as session:
            if not session.get(Automation, automation_id) or not session.get(DeliveryRecipient, recipient_id):
                raise AutomationConfigurationError("Automation or recipient was not found.")
            subscription = session.query(DeliverySubscription).filter_by(
                automation_id=automation_id, recipient_id=recipient_id
            ).one_or_none()
            if subscription is None:
                subscription = DeliverySubscription(automation_id=automation_id, recipient_id=recipient_id)
                session.add(subscription)
            subscription.enabled = enabled
            subscription.schedule_type = schedule_type
            subscription.weekday = weekday if schedule_type == "WEEKLY" else None
            subscription.run_time_utc = run_time_utc
            session.commit()
            session.refresh(subscription)
            return subscription

    def run_now(
        self,
        automation_id: int,
        *,
        trigger: str = "MANUAL",
        scheduled_at: datetime | None = None,
    ) -> AutomationRun:
        """Generate one artifact and dispatch only through an explicitly configured channel."""
        self.bootstrap_defaults()
        with self._session_factory() as session:
            automation = session.get(Automation, automation_id)
            if automation is None:
                raise AutomationConfigurationError("Automation was not found.")
            run = AutomationRun(
                automation_id=automation.id,
                trigger=trigger,
                status="RUNNING",
                started_at=scheduled_at or _utcnow(),
            )
            session.add(run)
            session.commit()
            run_id = run.id

        try:
            artifact = self._build_artifact(automation_id, run_id)
            with self._session_factory() as session:
                automation = session.get(Automation, automation_id)
                recipients = self._active_recipients(session, automation, scheduled_at)
                run = session.get(AutomationRun, run_id)
                run.artifact_path = str(artifact)
                run.recipient_count = len(recipients)
                run.delivered_count = self._dispatch(automation, recipients, artifact, run_id)
                run.status = "SUCCESS"
                run.completed_at = _utcnow()
                session.commit()
                session.refresh(run)
                return run
        except Exception as exc:
            with self._session_factory() as session:
                run = session.get(AutomationRun, run_id)
                run.status = "FAILED"
                run.completed_at = _utcnow()
                run.error_message = str(exc)[:4000]
                session.commit()
                session.refresh(run)
                return run

    def recent_runs(self, limit: int = 25) -> list[AutomationRun]:
        with self._session_factory() as session:
            return session.query(AutomationRun).order_by(AutomationRun.id.desc()).limit(limit).all()

    def run_due(self, now: datetime | None = None) -> list[AutomationRun]:
        """Run due enabled tasks once per minute; suitable for cron or a worker.

        This intentionally does not start a hidden scheduler inside a web
        process. A production web deployment will run this method from a
        single dedicated worker, avoiding duplicate deliveries across web
        replicas.
        """
        now = (now or _utcnow()).replace(second=0, microsecond=0)
        with self._session_factory() as session:
            tasks = session.query(Automation).filter(Automation.enabled.is_(True)).all()
            due_ids = []
            for task in tasks:
                if not self._task_or_recipient_is_due(session, task, now):
                    continue
                already_run = (
                    session.query(AutomationRun.id)
                    .filter(
                        AutomationRun.automation_id == task.id,
                        AutomationRun.trigger == "SCHEDULED",
                        AutomationRun.started_at >= now,
                    )
                    .first()
                )
                if not already_run:
                    due_ids.append(task.id)
        return [self.run_now(task_id, trigger="SCHEDULED", scheduled_at=now) for task_id in due_ids]

    def _active_recipients(
        self,
        session: Session,
        automation: Automation,
        scheduled_at: datetime | None,
    ) -> list[DeliveryRecipient]:
        rows = (
            session.query(DeliveryRecipient, DeliverySubscription)
            .join(DeliverySubscription, DeliverySubscription.recipient_id == DeliveryRecipient.id)
            .filter(
                DeliveryRecipient.enabled.is_(True),
                DeliverySubscription.automation_id == automation.id,
                DeliverySubscription.enabled.is_(True),
            )
            .order_by(DeliveryRecipient.slot)
            .all()
        )
        if scheduled_at is None:
            return [recipient for recipient, _ in rows]
        return [
            recipient for recipient, subscription in rows
            if self._subscription_is_due(automation, subscription, scheduled_at)
        ]

    def _task_or_recipient_is_due(self, session: Session, automation: Automation, now: datetime) -> bool:
        if self._cadence_is_due(automation.schedule_type, automation.weekday, automation.run_time_utc, now):
            return True
        subscriptions = session.query(DeliverySubscription).filter(
            DeliverySubscription.automation_id == automation.id,
            DeliverySubscription.enabled.is_(True),
        )
        return any(self._subscription_is_due(automation, subscription, now) for subscription in subscriptions)

    def _subscription_is_due(
        self,
        automation: Automation,
        subscription: DeliverySubscription,
        now: datetime,
    ) -> bool:
        schedule_type = subscription.schedule_type
        if schedule_type == "INHERIT":
            schedule_type = automation.schedule_type
            weekday = automation.weekday
            run_time = automation.run_time_utc
        else:
            weekday = subscription.weekday
            run_time = subscription.run_time_utc or automation.run_time_utc
        return self._cadence_is_due(schedule_type, weekday, run_time, now)

    @staticmethod
    def _cadence_is_due(schedule_type: str, weekday: int | None, run_time_utc: str, now: datetime) -> bool:
        if now.strftime("%H:%M") != run_time_utc:
            return False
        if schedule_type == "DAILY":
            return True
        return schedule_type == "WEEKLY" and weekday == now.weekday()

    def _build_artifact(self, automation_id: int, run_id: int) -> Path:
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        with self._session_factory() as session:
            automation = session.get(Automation, automation_id)
            timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
            if automation.task_type == TASK_WORKLOAD_EXPORT:
                artifact = self._outbox_dir / f"workload-export-{timestamp}-run-{run_id}.csv"
                self._write_workload_export(session, artifact)
            elif automation.task_type == TASK_COMPATIBILITY_REPORT:
                artifact = self._outbox_dir / f"compatibility-report-{timestamp}-run-{run_id}.txt"
                self._write_compatibility_report(session, artifact)
            else:
                raise AutomationConfigurationError("Unsupported automation task type.")
        return artifact

    @staticmethod
    def _write_workload_export(session: Session, artifact: Path) -> None:
        workloads = (
            session.query(IllumioWorkload)
            .options(joinedload(IllumioWorkload.labels).joinedload(IllumioWorkloadLabel.label))
            .order_by(IllumioWorkload.hostname, IllumioWorkload.id)
            .all()
        )
        def _safe_csv_cell(val: object) -> str:
            """I-6: Neutralize CSV formula injection characters for spreadsheet viewers."""
            text = "" if val is None else str(val)
            if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
                return f"'{text}"
            return text

        with artifact.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "illumio_href", "hostname", "name", "online", "connectivity_status",
                    "enforcement_mode", "ven_version", "os", "last_seen_at", "labels_json",
                ),
            )
            writer.writeheader()
            for workload in workloads:
                labels = {
                    association.label.label_type: association.label.value
                    for association in workload.labels
                    if association.label is not None
                }
                writer.writerow({
                    "illumio_href": _safe_csv_cell(workload.illumio_href),
                    "hostname": _safe_csv_cell(workload.hostname),
                    "name": _safe_csv_cell(workload.name),
                    "online": "" if workload.online is None else str(workload.online),
                    "connectivity_status": _safe_csv_cell(workload.connectivity_status),
                    "enforcement_mode": _safe_csv_cell(workload.enforcement_mode),
                    "ven_version": _safe_csv_cell(workload.ven_version),
                    "os": _safe_csv_cell(workload.os),
                    "last_seen_at": workload.last_seen_at.isoformat() if workload.last_seen_at else "",
                    "labels_json": json.dumps(labels, sort_keys=True),
                })

    @staticmethod
    def _write_compatibility_report(session: Session, artifact: Path) -> None:
        run = (
            session.query(ReconciliationRun)
            .filter(ReconciliationRun.status == "SUCCESS")
            .order_by(ReconciliationRun.completed_at.desc(), ReconciliationRun.id.desc())
            .first()
        )
        lines = ["Illumio Compatibility Report", f"Generated (UTC): {_utcnow().isoformat()}", ""]
        if run is None:
            lines.append("No successful reconciliation run is available yet.")
        else:
            lines.extend((
                f"Reconciliation run: {run.id}",
                f"Completed (UTC): {run.completed_at.isoformat() if run.completed_at else 'not recorded'}",
                f"Matched workloads: {run.matched_workloads}",
                f"Label mismatches: {run.label_mismatches}",
                f"Missing labels: {run.label_missing}",
                f"Missing in Illumio: {run.missing_in_illumio}",
                f"Orphaned in Illumio: {run.orphaned_in_illumio}",
                f"Ambiguous matches: {run.ambiguous_matches}",
                f"Actionable results: {run.actionable_results}",
            ))
        artifact.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _dispatch(
        self,
        automation: Automation,
        recipients: Iterable[DeliveryRecipient],
        artifact: Path,
        run_id: int,
    ) -> int:
        recipients = list(recipients)
        channels = self._normalize_delivery_channels(automation.delivery_channel)
        if CHANNEL_LOCAL_OUTBOX in channels:
            manifest = self._outbox_dir / f"delivery-manifest-run-{run_id}.json"
            manifest.write_text(json.dumps({
                "delivery": list(channels),
                "artifact": str(artifact),
                "recipients_not_emailed": [
                    {"slot": item.slot, "name": item.display_name, "email": item.email}
                    for item in recipients
                ],
            }, indent=2), encoding="utf-8")
        external_channels = set(channels) - {CHANNEL_LOCAL_OUTBOX}
        if external_channels and os.getenv("AUTOMATION_ENABLE_EXTERNAL_DELIVERY", "false").casefold() != "true":
            raise AutomationConfigurationError(
                "External delivery is disabled. Keep LOCAL_OUTBOX for testing, or set "
                "AUTOMATION_ENABLE_EXTERNAL_DELIVERY=true only after approval."
            )
        delivered_count = 0
        if CHANNEL_SMTP in channels:
            delivered_count += self._send_smtp(automation, recipients, artifact)
        if CHANNEL_BOX in channels:
            self._upload_box(automation, artifact)
        return delivered_count

    @staticmethod
    def _send_smtp(automation: Automation, recipients: list[DeliveryRecipient], artifact: Path) -> int:
        if not recipients:
            return 0
        host = os.getenv("AUTOMATION_SMTP_HOST", "").strip()
        sender = os.getenv("AUTOMATION_SMTP_FROM", "").strip()
        if not host or not sender:
            raise AutomationConfigurationError("SMTP host and sender must be configured in environment variables.")
        message = EmailMessage()
        message["Subject"] = f"Illumio {automation.display_name}"
        message["From"] = sender
        message["To"] = ", ".join(item.email for item in recipients)
        message.set_content("Attached is the scheduled Illumio pilot artifact.")
        message.add_attachment(artifact.read_bytes(), maintype="application", subtype="octet-stream", filename=artifact.name)
        port = int(os.getenv("AUTOMATION_SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=30) as client:
            if os.getenv("AUTOMATION_SMTP_STARTTLS", "true").casefold() == "true":
                # M-8: Pass an explicit default SSL context to enforce cert validation.
                tls_context = ssl.create_default_context()
                client.starttls(context=tls_context)
            username = os.getenv("AUTOMATION_SMTP_USERNAME", "")
            password = os.getenv("AUTOMATION_SMTP_PASSWORD", "")
            if username:
                client.login(username, password)
            client.send_message(message)
        return len(recipients)

    @staticmethod
    def _upload_box(automation: Automation, artifact: Path) -> None:
        token = os.getenv("BOX_ACCESS_TOKEN", "").strip()
        if not token or not automation.box_folder_id:
            raise AutomationConfigurationError("Box access token and destination folder ID must be configured.")
        attributes = json.dumps({"name": artifact.name, "parent": {"id": automation.box_folder_id}})
        with artifact.open("rb") as file_handle:
            response = requests.post(
                "https://upload.box.com/api/2.0/files/content",
                headers={"Authorization": f"Bearer {token}"},
                data={"attributes": attributes},
                files={"file": (artifact.name, file_handle, "application/octet-stream")},
                timeout=60,
            )
        response.raise_for_status()


def copy_artifact_to(destination: Path, artifact: Path) -> Path:
    """Utility for a future protected download endpoint; preserves the original."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(artifact, destination))
