import datetime
import uuid
from typing import Dict, List, Optional, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.domain.interfaces import JobRepository
from app.domain.entities import JobStatus
from app.repositories.database import JobModel

class SQLAlchemyJobRepository(JobRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    def _model_to_dict(self, model: JobModel) -> Dict[str, Any]:
        return {
            "id": model.id,
            "subject": model.subject,
            "difficulty": model.difficulty,
            "items_requested": model.items_requested,
            "status": JobStatus(model.status),
            "total_cost": model.total_cost,
            "error_message": model.error_message,
            "idempotency_key": model.idempotency_key,
            "request_hash": model.request_hash,
            "created_at": model.created_at,
            "updated_at": model.updated_at
        }

    async def create(self, subject: str, difficulty: str, items_requested: int, idempotency_key: Optional[str] = None, request_hash: Optional[str] = None) -> Dict[str, Any]:
        async with self.session_factory() as session:
            job = JobModel(
                id=str(uuid.uuid4()),
                subject=subject,
                difficulty=difficulty,
                items_requested=items_requested,
                status=JobStatus.PENDING.value,
                idempotency_key=idempotency_key,
                request_hash=request_hash
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return self._model_to_dict(job)

    async def get_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(JobModel).where(JobModel.id == job_id)
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            return self._model_to_dict(job) if job else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(JobModel).where(JobModel.idempotency_key == idempotency_key)
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            return self._model_to_dict(job) if job else None

    async def get_by_request_hash(self, request_hash: str) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(JobModel).where(JobModel.request_hash == request_hash)
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            return self._model_to_dict(job) if job else None

    async def update_status(self, job_id: str, status: JobStatus, error_message: Optional[str] = None) -> None:
        async with self.session_factory() as session:
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id)
                .values(status=status.value, error_message=error_message, updated_at=datetime.datetime.utcnow())
            )
            await session.execute(stmt)
            await session.commit()

    async def update_metrics(self, job_id: str, total_cost: float, total_duration_seconds: float) -> None:
        async with self.session_factory() as session:
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id)
                .values(total_cost=total_cost, updated_at=datetime.datetime.utcnow())
            )
            await session.execute(stmt)
            await session.commit()

    async def update_heartbeat(self, job_id: str) -> None:
        async with self.session_factory() as session:
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id)
                .values(updated_at=datetime.datetime.utcnow())
            )
            await session.execute(stmt)
            await session.commit()

    async def get_uncompleted_jobs(self) -> List[Dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(JobModel).where(JobModel.status.in_([JobStatus.PENDING.value, JobStatus.PROCESSING.value, JobStatus.QUEUED.value]))
            result = await session.execute(stmt)
            jobs = result.scalars().all()
            return [self._model_to_dict(j) for j in jobs]
