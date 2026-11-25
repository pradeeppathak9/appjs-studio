"""payments through autorev

apps: gateway credentials and test/live mode move to autorev (../autorev). An app keeps
`payment_provider` and gains the autorev app it bills through: its id, and its API key and webhook
signing secret (Fernet, like the other app secrets). The public Razorpay Key ID and PhonePe Merchant ID
are dropped; autorev holds them with their secrets.

payment_orders: one row per checkout. payment_events: autorev's webhooks, each applied once.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-26 01:46:55.946925
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_payment_events_app_id_apps"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        sa.UniqueConstraint("delivery_id", name=op.f("uq_payment_events_delivery_id")),
    )
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("app_user_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("gateway", sa.String(length=16), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("autorev_subscription_id", sa.String(length=64), nullable=True),
        sa.Column("gateway_order_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','active','failed','cancelled')", name=op.f("ck_payment_orders_status")
        ),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_payment_orders_app_id_apps"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_users.id"],
            name=op.f("fk_payment_orders_app_user_id_app_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name=op.f("fk_payment_orders_plan_id_plans")),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_payment_orders_subscription_id_subscriptions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_orders")),
        sa.UniqueConstraint(
            "autorev_subscription_id", name=op.f("uq_payment_orders_autorev_subscription_id")
        ),
    )
    op.create_index(
        "ix_payment_orders_user",
        "payment_orders",
        ["app_user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.add_column("apps", sa.Column("autorev_app_id", sa.String(length=64), nullable=True))
    op.add_column("apps", sa.Column("autorev_api_key_enc", sa.Text(), nullable=True))
    op.add_column("apps", sa.Column("autorev_webhook_secret_enc", sa.Text(), nullable=True))
    op.create_index(op.f("ix_apps_autorev_app_id"), "apps", ["autorev_app_id"], unique=False)
    op.drop_column("apps", "razorpay_key_id")
    op.drop_column("apps", "phonepe_merchant_id")
    op.drop_column("apps", "payment_mode")


def downgrade() -> None:
    op.add_column(
        "apps",
        sa.Column(
            "payment_mode",
            sa.VARCHAR(length=8),
            server_default=sa.text("'test'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.create_check_constraint(op.f("ck_apps_payment_mode"), "apps", "payment_mode IN ('test','live')")
    op.add_column(
        "apps", sa.Column("phonepe_merchant_id", sa.VARCHAR(length=64), autoincrement=False, nullable=True)
    )
    op.add_column(
        "apps", sa.Column("razorpay_key_id", sa.VARCHAR(length=64), autoincrement=False, nullable=True)
    )
    op.drop_index(op.f("ix_apps_autorev_app_id"), table_name="apps")
    op.drop_column("apps", "autorev_webhook_secret_enc")
    op.drop_column("apps", "autorev_api_key_enc")
    op.drop_column("apps", "autorev_app_id")
    op.drop_index("ix_payment_orders_user", table_name="payment_orders")
    op.drop_table("payment_orders")
    op.drop_table("payment_events")
