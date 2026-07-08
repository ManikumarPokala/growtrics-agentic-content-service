from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Type
from pydantic import BaseModel
from app.domain.entities import JobStatus, ItemStatus

class LLMProvider(ABC):
    @abstractmethod
    async def generate_structured_output(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Type[BaseModel], 
        temperature: float = 0.2
    ) -> Tuple[BaseModel, Dict[str, any]]:
        """
        Sends structured prompts to LLM and returns response schema + token & latency metadata.
        Returns:
            Tuple[response_data_instance, metadata_dict]
            metadata_dict should contain:
              "input_tokens": int
              "output_tokens": int
              "latency_ms": int
              "model": str
        """
        pass

class JobRepository(ABC):
    @abstractmethod
    async def create(self, subject: str, difficulty: str, items_requested: str, idempotency_key: Optional[str] = None, request_hash: Optional[str] = None) -> Dict[str, any]:
        pass

    @abstractmethod
    async def get_by_id(self, job_id: str) -> Optional[Dict[str, any]]:
        pass

    @abstractmethod
    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, any]]:
        pass

    @abstractmethod
    async def get_by_request_hash(self, request_hash: str) -> Optional[Dict[str, any]]:
        pass

    @abstractmethod
    async def update_status(self, job_id: str, status: JobStatus, error_message: Optional[str] = None) -> None:
        pass

    @abstractmethod
    async def update_metrics(self, job_id: str, total_cost: float, total_duration_seconds: float) -> None:
        pass

    @abstractmethod
    async def update_heartbeat(self, job_id: str) -> None:
        pass

    @abstractmethod
    async def get_uncompleted_jobs(self) -> List[Dict[str, any]]:
        pass


class ItemRepository(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    async def get_by_id(self, item_id: str) -> Optional[Dict[str, any]]:
        pass

    @abstractmethod
    async def get_items_by_job_id(self, job_id: str) -> List[Dict[str, any]]:
        pass

    @abstractmethod
    async def get_completed_count_by_job_id(self, job_id: str) -> int:
        pass

    @abstractmethod
    async def update_status_and_attempts(self, item_id: str, status: ItemStatus, attempts: int, cost_increment: float = 0.0) -> None:
        pass

    @abstractmethod
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
        pass


class EventRepository(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    async def get_events_by_job_id(self, job_id: str) -> List[Dict[str, any]]:
        pass
