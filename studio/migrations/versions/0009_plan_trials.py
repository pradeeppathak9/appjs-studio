"""plan trials

plans: trial_enabled, trial_days, trial_credits (an admin switches a free trial on per plan).
subscriptions: is_trial, and at most one trial subscription per app user.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-26 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans", sa.Column("trial_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column("plans", sa.Column("trial_days", sa.Integer(), server_default="7", nullable=False))
    op.add_column("plans", sa.Column("trial_credits", sa.Integer(), server_default="10", nullable=False))
    op.create_check_constraint(
        op.f("ck_plans_trial"), "plans", "trial_days BETWEEN 1 AND 365 AND trial_credits >= 0"
    )
    op.add_column(
        "subscriptions", sa.Column("is_trial", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.create_index(
        "ux_subscriptions_one_trial",
        "subscriptions",
        ["app_user_id"],
        unique=True,
        postgresql_where=sa.text("is_trial"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_subscriptions_one_trial", table_name="subscriptions", postgresql_where=sa.text("is_trial")
    )
    op.drop_column("subscriptions", "is_trial")
    op.drop_constraint(op.f("ck_plans_trial"), "plans", type_="check")
    op.drop_column("plans", "trial_credits")
    op.drop_column("plans", "trial_days")
    op.drop_column("plans", "trial_enabled")
