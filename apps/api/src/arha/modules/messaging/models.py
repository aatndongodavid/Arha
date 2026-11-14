from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column

from arha.db.base import Base
from arha.db.types import UUIDPK, TSNow


class MessageLog(Base):
    __tablename__ = "message_logs"
    id: Mapped[UUIDPK]
    organization_id: Mapped[uuid.UUID | None]
    channel: Mapped[str]
    template: Mapped[str]
    to_hash: Mapped[str]
    status: Mapped[str]
    cost_units: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[TSNow]
