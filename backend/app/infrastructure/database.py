from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        url = f"sqlite+pysqlite:///{self.path.as_posix()}"
        self.engine: Engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 5.0},
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        event.listen(self.engine, "connect", self._configure_connection)

    @staticmethod
    def _configure_connection(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA synchronous = FULL")
        finally:
            cursor.close()

    def configure_database(self) -> None:
        with self.engine.begin() as connection:
            mode = connection.execute(text("PRAGMA journal_mode = WAL")).scalar_one()
            if str(mode).lower() != "wal":
                raise RuntimeError(f"无法启用 SQLite WAL，当前模式为 {mode}")
            connection.execute(text("PRAGMA wal_autocheckpoint = 1000"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def check_health(self) -> bool:
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    def dispose(self) -> None:
        self.engine.dispose()

