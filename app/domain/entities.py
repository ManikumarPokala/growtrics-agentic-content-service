from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class JobStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ItemStatus(str, Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    VALIDATED = "VALIDATED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"

class StageType(str, Enum):
    GENERATION = "GENERATION"
    VALIDATION = "VALIDATION"
    REPAIR = "REPAIR"

class EventStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

class ChoiceKey(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"

class QuestionItem(BaseModel):
    question: str = Field(..., description="The stem or text of the multiple choice question")
    choices: Dict[str, str] = Field(..., description="Exactly 4 key-value pairs (A, B, C, D) representing unique choices")
    correct_answer: str = Field(..., description="The key of the correct choice (must be 'A', 'B', 'C', or 'D')")
    explanation: str = Field(..., description="Short explanation detailing why the correct answer is correct and others are wrong")

class JudgeRubric(BaseModel):
    schema_valid: bool = Field(..., description="True if choices contains exactly A, B, C, D and correct_answer is one of them")
    difficulty_alignment: float = Field(..., description="Score between 0.0 and 1.0 indicating how well the question matches the target difficulty")
    factuality_score: float = Field(..., description="Score between 0.0 and 1.0 indicating the factual correctness of the question and correct answer choice")
    clarity_score: float = Field(..., description="Score between 0.0 and 1.0 indicating clarity, correct grammar, and readability")
    explanation_alignment: bool = Field(..., description="True if the explanation correctly maps to the correct answer choice")
    overall_passed: bool = Field(..., description="True if all scores are >= 0.8 and schema/explanation validations pass")
    feedback: str = Field(..., description="Detailed feedback highlighting why the item passed or specific errors to be repaired")
