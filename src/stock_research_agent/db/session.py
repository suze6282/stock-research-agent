from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from stock_research_agent.config import Settings


def create_engine_from_settings(settings: Settings) -> Engine:
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is required to create a database engine")

    if "connect_timeout" in make_url(settings.database_url).query:
        return create_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_pre_ping=True,
        )

    return create_engine(
        settings.database_url,
        connect_args={"connect_timeout": 5},
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
        close_resets_only=False,
    )


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
