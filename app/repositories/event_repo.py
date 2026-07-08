import datetime
import uuid
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.domain.interfaces import EventRepository
from app.repositories.database import JobEventModel

class SQLAlchemyEventRepository(EventRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    def _model_to_dict(self, model: JobEventModel) -> Dict[str, any]:
        return {
            "id": model.id,
            "job_id": model.job_id,
            "stage": model.stage,
            "status": model.status,
            "timestamp": model.timestamp,
            "duration_ms": model.duration_ms,
            "input_tokens": model.input_tokens,
            "output_tokens": model.output_tokens,
            "cost": model.cost,
            "model": model.model,
            "error_message": model.error_message
        }

    async def log_event(
        self, 
        job_id: str, 
        stage: str, 
        status: str, 
        duration_ms: int, 
        input_tokens: int, 
        output_tokens: int, 
        cost: float, 
        model: str, 
        error_message: Optional[str] = None
    ) -> None:
        async with self.session_factory() as session:
            event = JobEventModel(
                id=str(uuid.uuid4()),
                job_id=job_id,
                stage=stage,
                status=status,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                model=model,
                error_message=error_message
            )
            session.add(event)
            await session.commit()

    async def get_events_by_job_id(self, job_id: str) -> List[Dict[str, any]]:
        async with self.session_factory() as session:
            stmt = select(JobEventModel).where(JobEventModel.job_id == job_id)
            result = await session.execute(stmt)
            events = result.scalars().all()
            return [self._model_to_dict(event) for event in events]
