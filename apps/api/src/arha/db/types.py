from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from sqlalchemy import BigInteger, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

from arha.core.ids import uuid7

UUIDPK = Annotated[uuid.UUID, mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)]
UUIDCol = Annotated[uuid.UUID, mapped_column(UUID(as_uuid=True))]
OrgId = Annotated[uuid.UUID, mapped_column(UUID(as_uuid=True), nullable=False,
                                           server_default=text("app_org()"))]
TS = Annotated[datetime, mapped_column(DateTime(timezone=True))]
TSNow = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=text("now()"))]
Money = Annotated[int, mapped_column(BigInteger)]
Json = Annotated[dict[str, Any], mapped_column(JSONB)]
JsonList = Annotated[list[Any], mapped_column(JSONB)]
