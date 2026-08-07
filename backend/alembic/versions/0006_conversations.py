"""follow-up conversations, stored chat URL and per-user onboarding flag

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("conversation_url", sa.String(512), nullable=True))
    op.add_column("prompts", sa.Column("follow_up_to", sa.String(32), nullable=True))
    op.create_index("ix_prompts_follow_up_to", "prompts", ["follow_up_to"])
    op.add_column("users", sa.Column(
        "onboarded", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "onboarded")
    op.drop_index("ix_prompts_follow_up_to", table_name="prompts")
    op.drop_column("prompts", "follow_up_to")
    op.drop_column("prompts", "conversation_url")
