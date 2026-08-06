"""remove external AI API integrations: browser-only architecture

Drops the api_keys table, per-prompt provider/model/token/cost columns,
and the scheduled-prompt provider column. All processing goes through the
master computer's ChatGPT browser session.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("api_keys")
    for col in ("provider", "model", "input_tokens", "output_tokens", "cost_usd"):
        op.drop_column("prompts", col)
    op.drop_column("scheduled_prompts", "provider")


def downgrade() -> None:
    op.add_column("scheduled_prompts",
                  sa.Column("provider", sa.String(32), nullable=False, server_default=""))
    op.add_column("prompts", sa.Column("provider", sa.String(32), nullable=False, server_default=""))
    op.add_column("prompts", sa.Column("model", sa.String(64), nullable=False, server_default=""))
    op.add_column("prompts", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("prompts", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("prompts", sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"))
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
