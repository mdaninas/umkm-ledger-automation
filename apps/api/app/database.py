from collections.abc import Generator
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, database_url: str) -> None:
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if database_url.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    def dispose(self) -> None:
        self.engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_db_session(request: Request) -> Generator[Session, None, None]:
    database: Database = request.app.state.database
    session = database.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
