from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def database_url(raw: str | None = None) -> URL:
    """DATABASE_URL, plus DATABASE_USER / DATABASE_PASSWORD when set (SQL Server authentication).
    Without a user, SQL Server uses Windows authentication."""
    url = make_url(raw or settings.database_url)
    if settings.database_user and not url.username and not url.drivername.startswith("sqlite"):
        url = url.set(username=settings.database_user, password=settings.database_password)
    return url


_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    database_url(),
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Network databases (SQL Server) drop idle connections; test each one before use.
    pool_pre_ping=not _is_sqlite,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def create_schema() -> None:
    """Create missing tables, then add columns introduced after a database was created.
    (create_all() never alters existing tables. Use Alembic once the schema changes regularly.)"""
    Base.metadata.create_all(engine)
    added = [  # (table, column, SQLite definition, SQL Server definition)
        ("applications", "web_origins", "JSON DEFAULT '[]'", "NVARCHAR(max) NOT NULL DEFAULT '[]'"),
        ("users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0", "BIT NOT NULL DEFAULT 0"),
        ("access_requests", "reason", "VARCHAR(500) NOT NULL DEFAULT ''", "NVARCHAR(500) NOT NULL DEFAULT ''"),
    ]
    for table, column, sqlite_def, mssql_def in added:
        if column not in {c["name"] for c in inspect(engine).get_columns(table)}:
            definition = sqlite_def if _is_sqlite else mssql_def
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD {'COLUMN ' if _is_sqlite else ''}{column} {definition}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
