"""app phone sign-in provider

apps: phone_provider (msg91|firebase), the app's own MSG91 template, OTP variable and encrypted auth
key, and its Firebase project id.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-23 20:40:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "apps", sa.Column("phone_provider", sa.String(length=16), server_default="msg91", nullable=False)
    )
    op.add_column("apps", sa.Column("msg91_template_id", sa.String(length=64), nullable=True))
    op.add_column("apps", sa.Column("msg91_otp_var", sa.String(length=32), nullable=True))
    op.add_column("apps", sa.Column("msg91_auth_key_enc", sa.Text(), nullable=True))
    op.add_column("apps", sa.Column("firebase_project_id", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        op.f("ck_apps_phone_provider"), "apps", "phone_provider IN ('msg91','firebase')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_apps_phone_provider"), "apps", type_="check")
    op.drop_column("apps", "firebase_project_id")
    op.drop_column("apps", "msg91_auth_key_enc")
    op.drop_column("apps", "msg91_otp_var")
    op.drop_column("apps", "msg91_template_id")
    op.drop_column("apps", "phone_provider")
