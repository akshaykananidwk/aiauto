"""image size presets, regenerate lineage and internal utility jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column(
        "image_size", sa.String(32), nullable=False, server_default="auto"))
    op.add_column("prompts", sa.Column("parent_id", sa.String(32), nullable=True))
    op.add_column("prompts", sa.Column(
        "is_utility", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_prompts_is_utility", "prompts", ["is_utility"])


def downgrade() -> None:
    op.drop_index("ix_prompts_is_utility", table_name="prompts")
    op.drop_column("prompts", "is_utility")
    op.drop_column("prompts", "parent_id")
    op.drop_column("prompts", "image_size")
