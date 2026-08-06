"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

user_role = sa.Enum("admin", "staff", name="user_role")
prompt_status = sa.Enum("waiting", "processing", "completed", "failed", "cancelled",
                        name="prompt_status")
file_kind = sa.Enum("upload", "result_image", "result_file", name="file_kind")
update_status = sa.Enum("running", "success", "failed", "rolled_back", name="update_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("full_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("department", sa.String(128), nullable=False, server_default=""),
        sa.Column("role", user_role, nullable=False, server_default="staff"),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False,
                  index=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("status", prompt_status, nullable=False, server_default="waiting",
                  index=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wants_image", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computer_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("department", sa.String(128), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "prompt_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prompt_id", sa.String(32),
                  sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", file_kind, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("rel_path", sa.String(512), nullable=False),
        sa.Column("thumb_rel_path", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=False,
                  server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True,
                  index=True),
        sa.Column("event", sa.String(64), nullable=False, index=True),
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "update_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_commit", sa.String(64), nullable=False, server_default=""),
        sa.Column("to_commit", sa.String(64), nullable=False, server_default=""),
        sa.Column("version", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", update_status, nullable=False, server_default="running"),
        sa.Column("log", sa.Text(), nullable=False, server_default=""),
        sa.Column("backup_path", sa.String(512), nullable=False, server_default=""),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("update_records")
    op.drop_table("app_settings")
    op.drop_table("audit_logs")
    op.drop_table("prompt_files")
    op.drop_table("prompts")
    op.drop_table("users")
    for enum in (update_status, file_kind, prompt_status, user_role):
        enum.drop(op.get_bind(), checkfirst=True)
