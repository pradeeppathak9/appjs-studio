"""app provider keys

apps: the app's own encrypted API keys for Gemini, OpenAI, fal and OpenRouter. Its jobs use them in
place of the server's keys.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-23 22:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

COLUMNS = ("gemini_api_key_enc", "openai_api_key_enc", "fal_api_key_enc", "openrouter_api_key_enc")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("apps", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column("apps", name)
