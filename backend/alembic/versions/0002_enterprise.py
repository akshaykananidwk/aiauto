"""enterprise features: templates, schedules, notifications, api keys,
quotas, provider/cost tracking, indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

schedule_type = sa.Enum("once", "interval", "daily", "weekly", name="schedule_type")


def upgrade() -> None:
    # users: quota overrides + telegram
    op.add_column("users", sa.Column("daily_limit", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("monthly_limit", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(64), nullable=True))

    # prompts: provider + usage accounting
    op.add_column("prompts", sa.Column("provider", sa.String(32), nullable=False, server_default=""))
    op.add_column("prompts", sa.Column("model", sa.String(64), nullable=False, server_default=""))
    op.add_column("prompts", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("prompts", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("prompts", sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"))
    op.add_column("prompts", sa.Column("scheduled_id", sa.Integer(), nullable=True))
    op.create_index("ix_prompts_user_created", "prompts", ["user_id", "created_at"])
    op.create_index("ix_audit_logs_created", "audit_logs", ["created_at"])

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="", index=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "template_favorites",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("template_id", sa.Integer(),
                  sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "scheduled_prompts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("wants_image", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(32), nullable=False, server_default=""),
        sa.Column("schedule_type", schedule_type, nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("run_at_time", sa.String(5), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_prompt_id", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("type", sa.String(32), nullable=False, server_default="info"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])
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
    op.create_table(
        "department_quotas",
        sa.Column("department", sa.String(128), primary_key=True),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("department_quotas")
    op.drop_table("api_keys")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("scheduled_prompts")
    op.drop_table("template_favorites")
    op.drop_table("prompt_templates")
    op.drop_index("ix_audit_logs_created", table_name="audit_logs")
    op.drop_index("ix_prompts_user_created", table_name="prompts")
    for col in ("scheduled_id", "cost_usd", "output_tokens", "input_tokens", "model", "provider"):
        op.drop_column("prompts", col)
    for col in ("telegram_chat_id", "monthly_limit", "daily_limit"):
        op.drop_column("users", col)
    schedule_type.drop(op.get_bind(), checkfirst=True)
