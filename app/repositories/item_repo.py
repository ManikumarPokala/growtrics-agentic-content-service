import datetime
import uuid
from typing import Dict, List, Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.domain.interfaces import ItemRepository
from app.domain.entities import ItemStatus
from app.repositories.database import ItemModel

class SQLAlchemyItemRepository(ItemRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    def _model_to_dict(self, model: ItemModel) -> Dict[str, any]:
        return {
            "id": model.id,
            "job_id": model.job_id,
            "question": model.question,
            "choices": model.choices,
            "correct_answer": model.correct_answer,
            "explanation": model.explanation,
            "cost": model.cost,
            "status": ItemStatus(model.status),
            "attempts": model.attempts,
            "created_at": model.created_at,
            "updated_at": model.updated_at
        }

    async def create(
        self, 
        job_id: str, 
        question: str, 
        choices: Dict[str, str], 
        correct_answer: str, 
        explanation: str, 
        cost: float, 
        status: ItemStatus,
        attempts: int = 1
    ) -> Dict[str, any]:
        async with self.session_factory() as session:
            item = ItemModel(
                id=str(uuid.uuid4()),
                job_id=job_id,
                question=question,
                choices=choices,
                correct_answer=correct_answer,
                explanation=explanation,
                cost=cost,
                status=status.value,
                attempts=attempts
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return self._model_to_dict(item)

    async def get_by_id(self, item_id: str) -> Optional[Dict[str, any]]:
        async with self.session_factory() as session:
            stmt = select(ItemModel).where(ItemModel.id == item_id)
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            return self._model_to_dict(item) if item else None

    async def get_items_by_job_id(self, job_id: str) -> List[Dict[str, any]]:
        async with self.session_factory() as session:
            stmt = select(ItemModel).where(ItemModel.job_id == job_id)
            result = await session.execute(stmt)
            items = result.scalars().all()
            return [self._model_to_dict(item) for item in items]

    async def get_completed_count_by_job_id(self, job_id: str) -> int:
        async with self.session_factory() as session:
            stmt = select(func.count(ItemModel.id)).where(
                ItemModel.job_id == job_id,
                ItemModel.status == ItemStatus.VALIDATED.value
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def update_status_and_attempts(self, item_id: str, status: ItemStatus, attempts: int, cost_increment: float = 0.0) -> None:
        async with self.session_factory() as session:
            stmt = (
                update(ItemModel)
                .where(ItemModel.id == item_id)
                .values(
                    status=status.value,
                    attempts=attempts,
                    cost=ItemModel.cost + cost_increment,
                    updated_at=datetime.datetime.utcnow()
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def update_item_content(
        self, 
        item_id: str, 
        question: str, 
        choices: Dict[str, str], 
        correct_answer: str, 
        explanation: str, 
        status: ItemStatus, 
        attempts: int, 
        cost_increment: float
    ) -> None:
        async with self.session_factory() as session:
            stmt = (
                update(ItemModel)
                .where(ItemModel.id == item_id)
                .values(
                    question=question,
                    choices=choices,
                    correct_answer=correct_answer,
                    explanation=explanation,
                    status=status.value,
                    attempts=attempts,
                    cost=ItemModel.cost + cost_increment,
                    updated_at=datetime.datetime.utcnow()
                )
            )
            await session.execute(stmt)
            await session.commit()
