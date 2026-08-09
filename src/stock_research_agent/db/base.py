from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base whose datetime annotations use PostgreSQL TIMESTAMPTZ."""

    type_annotation_map = {datetime: DateTime(timezone=True)}
