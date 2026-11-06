"""Database bootstrap helpers.

Production schema changes go through Alembic (``alembic upgrade head``).
``create_all`` is used for local development and the test suite only.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.models import Base
from app.db.session import apply_row_level_security, get_engine

logger = get_logger(__name__)


def create_all() -> None:
    Base.metadata.create_all(bind=get_engine())
    apply_row_level_security()
    logger.info("database_initialised")


def drop_all() -> None:
    Base.metadata.drop_all(bind=get_engine())
