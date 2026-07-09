from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, conint, constr, ConfigDict

class JobCreateRequest(BaseModel):
    subject: constr(min_length=2, max_length=100) = Field(
        ..., 
        description="The subject or topic for question generation, e.g. 'Secondary school chemistry'"
    )
    difficulty: constr(min_length=2, max_length=50) = Field(
        ..., 
        description="Target difficulty level, e.g. 'Beginner', 'Intermediate', 'Advanced'"
    )
    items_requested: conint(ge=1, le=20) = Field(
        ..., 
        description="Number of MCQs requested. Restricted to 1-20 to avoid rate limit/load spikes."
    )

class JobResponse(BaseModel):
    id: str
    subject: str
    difficulty: str
    items_requested: int
    status: str
    total_cost: float
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GeneratedItemResponse(BaseModel):
    id: str
    question: str
    choices: Dict[str, str]
    correct_answer: str
    explanation: str
    cost: float
    status: str
    attempts: int

    model_config = ConfigDict(from_attributes=True)

class JobMetricsResponse(BaseModel):
    total_duration_seconds: float
    total_cost_usd: float
    average_cost_per_item_usd: float
    pass_rate_percentage: float
    repair_rate_percentage: float
    total_llm_calls: int
    p50_latency_seconds: float
    p95_latency_seconds: float

class JobDetailsResponse(BaseModel):
    job: JobResponse
    metrics: JobMetricsResponse
    items: List[GeneratedItemResponse]
