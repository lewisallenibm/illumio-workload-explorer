"""Add safe, auditable scheduled-delivery configuration.

This is additive only. Existing desktop data, imports, and reconciliation
history remain untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260914_02"
down_revision = "20260902_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_type", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_type", sa.String(length=16), nullable=False, server_default="WEEKLY"),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("run_time_utc", sa.String(length=5), nullable=False, server_default="13:00"),
        sa.Column("delivery_channel", sa.String(length=32), nullable=False, server_default="LOCAL_OUTBOX"),
        sa.Column("box_folder_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "delivery_recipients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("slot", name="uq_delivery_recipients_slot"),
    )
    op.create_table(
        "delivery_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("automation_id", sa.Integer(), sa.ForeignKey("automations.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("delivery_recipients.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_type", sa.String(length=16), nullable=False, server_default="INHERIT"),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("run_time_utc", sa.String(length=5), nullable=True),
        sa.UniqueConstraint("automation_id", "recipient_id", name="uq_delivery_subscription"),
    )
    op.create_index("ix_delivery_subscriptions_automation_id", "delivery_subscriptions", ["automation_id"])
    op.create_index("ix_delivery_subscriptions_recipient_id", "delivery_subscriptions", ["recipient_id"])
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("automation_id", sa.Integer(), sa.ForeignKey("automations.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="MANUAL"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="RUNNING"),
        sa.Column("artifact_path", sa.String(length=1024), nullable=True),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_automation_runs_automation_id", "automation_runs", ["automation_id"])


def downgrade() -> None:
    op.drop_index("ix_automation_runs_automation_id", table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index("ix_delivery_subscriptions_recipient_id", table_name="delivery_subscriptions")
    op.drop_index("ix_delivery_subscriptions_automation_id", table_name="delivery_subscriptions")
    op.drop_table("delivery_subscriptions")
    op.drop_table("delivery_recipients")
    op.drop_table("automations")
