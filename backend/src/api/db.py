"""Database engine and session for the product tables. The engine is built on first use."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from api.model import database_url


@lru_cache
def engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    # Looked up at call time: tests replace `engine` with an in-memory database.
    with Session(engine(), expire_on_commit=False) as session:
        yield session
