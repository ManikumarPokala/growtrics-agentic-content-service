import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.domain.entities import JobStatus
from app.repositories.job_repo import SQLAlchemyJobRepository
from app.repositories.item_repo import SQLAlchemyItemRepository
from app.repositories.event_repo import SQLAlchemyEventRepository
from app.workers.queue_worker import BackgroundQueueWorker
from app.application.orchestrator import PipelineOrchestrator

@pytest_asyncio.fixture
async def client(session_factory, mock_provider):
    # Instantiate repositories using test session factory
    test_job_repo = SQLAlchemyJobRepository(session_factory)
    test_item_repo = SQLAlchemyItemRepository(session_factory)
    test_event_repo = SQLAlchemyEventRepository(session_factory)
    
    test_orchestrator = PipelineOrchestrator(
        job_repo=test_job_repo,
        item_repo=test_item_repo,
        event_repo=test_event_repo,
        primary_provider=mock_provider,
        fallback_provider=mock_provider
    )
    
    test_worker = BackgroundQueueWorker(job_repo=test_job_repo, orchestrator=test_orchestrator)
    # Start worker pool
    await test_worker.start()

    # Override app state variables
    app.state.job_repo = test_job_repo
    app.state.item_repo = test_item_repo
    app.state.event_repo = test_event_repo
    app.state.queue_worker = test_worker

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await test_worker.stop()

@pytest.mark.asyncio
async def test_create_and_poll_job(client):
    # 1. Post new Job request
    payload = {
        "subject": "Secondary school chemistry",
        "difficulty": "Beginner",
        "items_requested": 5
    }
    
    headers = {"X-Idempotency-Key": "test-idempotency-key-1"}
    response = await client.post("/api/jobs", json=payload, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["id"] is not None
    assert data["status"] in (JobStatus.QUEUED.value, JobStatus.PROCESSING.value, JobStatus.COMPLETED.value)
    assert data["subject"] == payload["subject"]
    
    job_id = data["id"]

    # 2. Test Idempotency with exact same key
    dup_response = await client.post("/api/jobs", json=payload, headers=headers)
    assert dup_response.status_code == 202
    dup_data = dup_response.json()
    assert dup_data["id"] == job_id # Verify exact same job ID returned

    # 3. Test Polling Status endpoint
    poll_response = await client.get(f"/api/jobs/{job_id}")
    assert poll_response.status_code == 200
    poll_data = poll_response.json()
    assert poll_data["id"] == job_id

    # 4. Wait for worker to finish processing (using mocks, it finishes almost instantly)
    # Poll until COMPLETED or FAILED
    for _ in range(10):
        res = await client.get(f"/api/jobs/{job_id}")
        if res.json()["status"] in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
            break
        import asyncio
        await asyncio.sleep(0.1)

    # 5. Fetch Job Results Details
    results_response = await client.get(f"/api/jobs/{job_id}/results")
    assert results_response.status_code == 200
    results_data = results_response.json()
    
    assert results_data["job"]["id"] == job_id
    assert "metrics" in results_data
    assert "items" in results_data
    assert len(results_data["items"]) == 5
    assert results_data["metrics"]["total_llm_calls"] > 0
    assert results_data["metrics"]["p50_latency_seconds"] >= 0.0
