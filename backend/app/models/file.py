from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class FileKind(str, enum.Enum):
    upload = "upload"          # sent by staff along with the prompt
    result_image = "result_image"
    result_file = "result_file"


class PromptFile(TimestampMixin, Base):
    __tablename__ = "prompt_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[str] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[FileKind] = mapped_column(Enum(FileKind, name="file_kind"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # path relative to the storage root (safe to move installations around)
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False)
    thumb_rel_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    prompt = relationship("Prompt", back_populates="files", lazy="noload")
