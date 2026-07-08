import pytest
import pytest_asyncio
from typing import Dict, Tuple, Type
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.repositories.database import Base
from app.repositories.job_repo import SQLAlchemyJobRepository
from app.repositories.item_repo import SQLAlchemyItemRepository
from app.repositories.event_repo import SQLAlchemyEventRepository
from app.domain.interfaces import LLMProvider
from app.domain.entities import QuestionItem, JudgeRubric

class MockLLMProvider(LLMProvider):
    def __init__(self):
        self.call_count = 0
        self.responses = []

    def add_response(self, response_instance: BaseModel, metadata: Dict[str, any] = None):
        if not metadata:
            metadata = {"input_tokens": 100, "output_tokens": 50, "latency_ms": 200, "cost": 0.00005, "model": "mock-model"}
        self.responses.append((response_instance, metadata))

    async def generate_structured_output(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Type[BaseModel], 
        temperature: float = 0.2
    ) -> Tuple[BaseModel, Dict[str, any]]:
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        
        # Default mock output based on requested schema
        if response_model == QuestionItem:
            mock_item = QuestionItem(
                question="What is the chemical symbol for Gold?",
                choices={"A": "Au", "B": "Ag", "C": "Fe", "D": "Cu"},
                correct_answer="A",
                explanation="Au is derived from the Latin word aurum, which means Gold."
            )
            return mock_item, {"input_tokens": 10, "output_tokens": 20, "latency_ms": 100, "cost": 0.00001, "model": "mock-model"}
        
        elif response_model == JudgeRubric:
            mock_rubric = JudgeRubric(
                schema_valid=True,
                difficulty_alignment=1.0,
                factuality_score=1.0,
                clarity_score=1.0,
                explanation_alignment=True,
                overall_passed=True,
                feedback="All checks passed."
            )
            return mock_rubric, {"input_tokens": 15, "output_tokens": 15, "latency_ms": 100, "cost": 0.00001, "model": "mock-model"}
            
        raise ValueError(f"No mock response configured for {response_model}")

@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture
async def job_repo(session_factory):
    return SQLAlchemyJobRepository(session_factory)

@pytest_asyncio.fixture
async def item_repo(session_factory):
    return SQLAlchemyItemRepository(session_factory)

@pytest_asyncio.fixture
async def event_repo(session_factory):
    return SQLAlchemyEventRepository(session_factory)

@pytest_asyncio.fixture
def mock_provider():
    return MockLLMProvider()
