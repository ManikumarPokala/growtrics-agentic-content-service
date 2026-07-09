import datetime
from typing import Dict, List, Optional
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON, ForeignKey, select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.core.config import settings

def utc_now_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), nullable=False)
    items_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    request_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

class ItemModel(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    choices: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(10), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

class JobEventModel(Base):
    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now_naive)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

# Create async engine and sessionmaker
# Set pool_pre_ping to check connection before using
# Set busy_timeout in connection options for SQLite WAL retry handling
connect_args = {"timeout": 30} # 30 seconds timeout for SQLite locking
engine = create_async_engine(
    settings.DATABASE_URL, 
    connect_args=connect_args,
    pool_pre_ping=True
)

async_session_factory = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        # Enable WAL mode for SQLite to support concurrency
        if settings.DATABASE_URL.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            await conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
        await conn.run_sync(Base.metadata.create_all)
