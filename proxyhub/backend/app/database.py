import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
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


async def init_db():
    from app.models import subscription, node, network, test_result  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
