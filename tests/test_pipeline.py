import pytest
from app.domain.entities import JobStatus, ItemStatus, StageType
from app.application.orchestrator import PipelineOrchestrator
from app.domain.entities import QuestionItem, JudgeRubric

@pytest.mark.asyncio
async def test_orchestrator_successful_flow(job_repo, item_repo, event_repo, mock_provider):
    # Setup orchestrator with mock provider for both primary and fallback
    orchestrator = PipelineOrchestrator(
        job_repo=job_repo,
        item_repo=item_repo,
        event_repo=event_repo,
        primary_provider=mock_provider,
        fallback_provider=mock_provider
    )

    # 1. Create a Job
    job = await job_repo.create(subject="Chemistry", difficulty="Beginner", items_requested=1)
    
    # 2. Run Job
    await orchestrator.execute_job(job["id"])

    # 3. Assertions
    updated_job = await job_repo.get_by_id(job["id"])
    assert updated_job["status"] == JobStatus.COMPLETED
    assert updated_job["total_cost"] > 0.0

    items = await item_repo.get_items_by_job_id(job["id"])
    assert len(items) == 1
    assert items[0]["status"] == ItemStatus.VALIDATED
    assert items[0]["attempts"] == 1

    events = await event_repo.get_events_by_job_id(job["id"])
    # 1 generation, 1 validation event
    assert len(events) == 2
    assert events[0]["stage"] == StageType.GENERATION.value
    assert events[1]["stage"] == StageType.VALIDATION.value

@pytest.mark.asyncio
async def test_orchestrator_repair_flow(job_repo, item_repo, event_repo, mock_provider):
    # Setup custom response sequence for mock provider:
    # 1. Initial MCQ Generation
    # 2. Judge Evaluation (Fails)
    # 3. Repair MCQ Generation
    # 4. Judge Evaluation (Passes)
    
    initial_mcq = QuestionItem(
        question="What is Gold?",
        choices={"A": "Au", "B": "Ag", "C": "Fe", "D": "Cu"},
        correct_answer="B",  # INCORRECT
        explanation="Ag is gold"
    )
    failed_rubric = JudgeRubric(
        schema_valid=True,
        difficulty_alignment=0.5,
        factuality_score=0.2,
        clarity_score=0.9,
        explanation_alignment=False,
        overall_passed=False,
        feedback="Ag is silver, Au is gold. Fix correct_answer and explanation."
    )
    repaired_mcq = QuestionItem(
        question="What is Gold?",
        choices={"A": "Au", "B": "Ag", "C": "Fe", "D": "Cu"},
        correct_answer="A",
        explanation="Au is derived from aurum, meaning Gold."
    )
    passed_rubric = JudgeRubric(
        schema_valid=True,
        difficulty_alignment=1.0,
        factuality_score=1.0,
        clarity_score=1.0,
        explanation_alignment=True,
        overall_passed=True,
        feedback="Factual correct."
    )
    
    mock_provider.add_response(initial_mcq)
    mock_provider.add_response(failed_rubric)
    mock_provider.add_response(repaired_mcq)
    mock_provider.add_response(passed_rubric)

    orchestrator = PipelineOrchestrator(
        job_repo=job_repo,
        item_repo=item_repo,
        event_repo=event_repo,
        primary_provider=mock_provider,
        fallback_provider=mock_provider
    )

    job = await job_repo.create(subject="Chemistry", difficulty="Beginner", items_requested=1)
    await orchestrator.execute_job(job["id"])

    updated_job = await job_repo.get_by_id(job["id"])
    assert updated_job["status"] == JobStatus.COMPLETED

    items = await item_repo.get_items_by_job_id(job["id"])
    assert len(items) == 1
    assert items[0]["status"] == ItemStatus.VALIDATED
    assert items[0]["attempts"] == 2 # 1 gen + 1 repair attempt

@pytest.mark.asyncio
async def test_orchestrator_failed_repair_to_hitl_flow(job_repo, item_repo, event_repo, mock_provider):
    # Setup custom response sequence for mock provider:
    # 1. Initial MCQ Generation
    # 2. Judge Evaluation (Fails)
    # 3. Repair MCQ Generation 1
    # 4. Judge Evaluation (Fails)
    # 5. Repair MCQ Generation 2 (MAX_REPAIR_ATTEMPTS = 2)
    # 6. Judge Evaluation (Fails)
    
    initial_mcq = QuestionItem(
        question="What is Gold?",
        choices={"A": "Au", "B": "Ag", "C": "Fe", "D": "Cu"},
        correct_answer="B",
        explanation="Ag is gold"
    )
    failed_rubric = JudgeRubric(
        schema_valid=True,
        difficulty_alignment=0.5,
        factuality_score=0.2,
        clarity_score=0.9,
        explanation_alignment=False,
        overall_passed=False,
        feedback="Ag is silver, Au is gold. Fix correct_answer."
    )
    
    mock_provider.add_response(initial_mcq) # Gen 1
    mock_provider.add_response(failed_rubric) # Judge 1
    mock_provider.add_response(initial_mcq) # Repair 1 (attempts = 2)
    mock_provider.add_response(failed_rubric) # Judge 2
    mock_provider.add_response(initial_mcq) # Repair 2 (attempts = 3)
    mock_provider.add_response(failed_rubric) # Judge 3
    
    orchestrator = PipelineOrchestrator(
        job_repo=job_repo,
        item_repo=item_repo,
        event_repo=event_repo,
        primary_provider=mock_provider,
        fallback_provider=mock_provider
    )

    job = await job_repo.create(subject="Chemistry", difficulty="Beginner", items_requested=1)
    await orchestrator.execute_job(job["id"])

    items = await item_repo.get_items_by_job_id(job["id"])
    assert len(items) == 1
    # Bounded retries exhausted -> Transitions to REQUIRES_REVIEW (HITL)
    assert items[0]["status"] == ItemStatus.REQUIRES_REVIEW
    assert items[0]["attempts"] == 3 # 1 initial + 2 repair attempts
