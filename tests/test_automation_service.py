from pathlib import Path
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.automation_service import (
    AutomationConfigurationError,
    AutomationService,
    CHANNEL_LOCAL_OUTBOX,
    CHANNEL_SMTP,
)


@pytest.fixture()
def service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'automation.sqlite'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return AutomationService(session_factory=session_factory, outbox_dir=tmp_path / "outbox")


def test_defaults_are_disabled_and_safe(service):
    tasks = service.bootstrap_defaults()

    assert [task.task_type for task in tasks] == ["WORKLOAD_EXPORT", "COMPATIBILITY_REPORT"]
    assert all(task.enabled is False for task in tasks)
    assert all(task.delivery_channel == CHANNEL_LOCAL_OUTBOX for task in tasks)


def test_recipient_slots_are_limited_and_validate_email(service):
    recipient = service.save_recipient(slot=1, display_name="Pilot User", email="pilot@example.test", enabled=True)

    assert recipient.slot == 1
    with pytest.raises(AutomationConfigurationError, match="between 1 and 10"):
        service.save_recipient(slot=11, display_name="Too Many", email="too-many@example.test", enabled=True)
    with pytest.raises(AutomationConfigurationError, match="valid recipient email"):
        service.save_recipient(slot=2, display_name="Bad", email="not-an-email", enabled=True)


def test_manual_workload_export_writes_local_artifact_and_audit_row(service):
    task = service.bootstrap_defaults()[0]
    recipient = service.save_recipient(slot=1, display_name="Pilot User", email="pilot@example.test", enabled=True)
    service.set_subscription(automation_id=task.id, recipient_id=recipient.id, enabled=True)

    run = service.run_now(task.id)

    assert run.status == "SUCCESS"
    assert run.recipient_count == 1
    assert run.delivered_count == 0
    artifact = Path(run.artifact_path)
    assert artifact.exists()
    assert artifact.read_text(encoding="utf-8").startswith("illumio_href,hostname")
    assert (artifact.parent / f"delivery-manifest-run-{run.id}.json").exists()


def test_external_delivery_has_an_explicit_runtime_gate(service):
    task = service.bootstrap_defaults()[0]
    service.update_automation(
        task.id,
        enabled=False,
        schedule_type="DAILY",
        weekday=None,
        run_time_utc="13:00",
        delivery_channels=CHANNEL_SMTP,
        box_folder_id=None,
    )

    run = service.run_now(task.id)

    assert run.status == "FAILED"
    assert "External delivery is disabled" in run.error_message


def test_due_runner_respects_schedule_and_does_not_duplicate_the_same_minute(service):
    task = service.bootstrap_defaults()[0]
    service.update_automation(
        task.id,
        enabled=True,
        schedule_type="DAILY",
        weekday=None,
        run_time_utc="13:00",
        delivery_channels=CHANNEL_LOCAL_OUTBOX,
        box_folder_id=None,
    )

    first = service.run_due(datetime(2026, 9, 14, 13, 0))
    duplicate = service.run_due(datetime(2026, 9, 14, 13, 0))
    not_due = service.run_due(datetime(2026, 9, 14, 13, 1))

    assert len(first) == 1
    assert first[0].status == "SUCCESS"
    assert duplicate == []
    assert not_due == []


def test_delivery_channels_can_include_email_and_box(service):
    task = service.bootstrap_defaults()[0]

    updated = service.update_automation(
        task.id,
        enabled=False,
        schedule_type="DAILY",
        weekday=None,
        run_time_utc="13:00",
        delivery_channels=[CHANNEL_LOCAL_OUTBOX, CHANNEL_SMTP, "BOX"],
        box_folder_id="pilot-folder",
    )

    assert updated.delivery_channel == "LOCAL_OUTBOX,SMTP,BOX"


def test_deleting_recipient_removes_its_subscriptions(service):
    task = service.bootstrap_defaults()[0]
    recipient = service.save_recipient(slot=1, display_name="Pilot User", email="pilot@example.test", enabled=True)
    service.set_subscription(automation_id=task.id, recipient_id=recipient.id, enabled=True)

    service.delete_recipient(slot=1)

    assert service.list_recipients() == []
    assert service.list_subscriptions() == {}
