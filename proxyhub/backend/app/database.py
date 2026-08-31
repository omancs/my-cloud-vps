import os
import secrets
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings

# Ensure database directory exists
_raw_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
if _raw_path:
    try:
        _dir = os.path.dirname(os.path.abspath(_raw_path))
        if _dir:
            Path(_dir).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _migrate_sqlite_schema(sync_conn):
    """Synchronously inspect and auto-add missing columns to existing SQLite tables."""
    # List of (table_name, column_name, column_def_sql)
    required_columns = [
        # networks
        ("networks", "token", "TEXT DEFAULT ''"),
        ("networks", "auto_update", "BOOLEAN DEFAULT 0"),
        ("networks", "sort_by", "VARCHAR(20) DEFAULT 'latency'"),
        ("networks", "description", "TEXT"),
        # nodes
        ("nodes", "youtube_unlock", "BOOLEAN DEFAULT 0"),
        ("nodes", "netflix_unlock", "BOOLEAN DEFAULT 0"),
        ("nodes", "openai_unlock", "BOOLEAN DEFAULT 0"),
        ("nodes", "is_residential", "BOOLEAN DEFAULT 0"),
        ("nodes", "purity_status", "VARCHAR(20) DEFAULT 'unknown'"),
        ("nodes", "real_latency_ms", "FLOAT"),
        ("nodes", "download_speed", "FLOAT"),
        ("nodes", "ip_address", "VARCHAR(64)"),
        ("nodes", "ip_country", "VARCHAR(10)"),
        ("nodes", "ip_org", "VARCHAR(200)"),
        # subscriptions
        ("subscriptions", "node_count", "INTEGER DEFAULT 0"),
        ("subscriptions", "last_fetched", "DATETIME"),
        ("subscriptions", "interval_minutes", "INTEGER DEFAULT 360"),
        ("subscriptions", "auto_refresh", "BOOLEAN DEFAULT 1"),
    ]

    # Check which tables exist
    res = sync_conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    existing_tables = {row[0] for row in res.fetchall()}

    for table, column, col_type in required_columns:
        if table not in existing_tables:
            continue
        # Check if column exists
        info_res = sync_conn.execute(text(f"PRAGMA table_info({table})"))
        existing_cols = {row[1] for row in info_res.fetchall()}
        if column not in existing_cols:
            try:
                sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                print(f"[DB Migration] Added missing column: {table}.{column}")
            except Exception as e:
                print(f"[DB Migration] Warning adding {table}.{column}: {e}")

    # Ensure all existing networks have a non-empty token
    if "networks" in existing_tables:
        try:
            net_rows = sync_conn.execute(text("SELECT id, token FROM networks")).fetchall()
            for r in net_rows:
                net_id, token = r[0], r[1]
                if not token:
                    new_token = secrets.token_hex(8)
                    sync_conn.execute(
                        text("UPDATE networks SET token = :t WHERE id = :id"),
                        {"t": new_token, "id": net_id}
                    )
        except Exception:
            pass


async def init_db():
    from app.models import subscription, node, network, test_result, traffic, rule  # noqa: F401
    async with engine.begin() as conn:
        # Create all tables that don't exist yet
        await conn.run_sync(Base.metadata.create_all)
        # Auto migrate existing SQLite tables to add new columns
        await conn.run_sync(_migrate_sqlite_schema)
    print("[Database] Initialized and auto-migrated successfully.")
