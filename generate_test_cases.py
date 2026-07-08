import os
import json
import asyncio
import logging
from app.repositories.database import init_db, async_session_factory
from app.repositories.job_repo import SQLAlchemyJobRepository
from app.repositories.item_repo import SQLAlchemyItemRepository
from app.repositories.event_repo import SQLAlchemyEventRepository
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.gemini import GeminiProvider
from app.application.orchestrator import PipelineOrchestrator
from app.workers.queue_worker import BackgroundQueueWorker
from app.domain.entities import JobStatus
from app.telemetry.metrics import calculate_job_metrics

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("growtrics.test_cases")

TEST_CASES = [
    {"subject": "Secondary school chemistry", "difficulty": "Beginner", "items": 5, "filename": "chemistry_beginner.json"},
    {"subject": "Secondary school chemistry", "difficulty": "Advanced", "items": 5, "filename": "chemistry_advanced.json"},
    {"subject": "Secondary school biology", "difficulty": "Intermediate", "items": 5, "filename": "biology_intermediate.json"}
]

async def run_test_case(case, job_repo, item_repo, event_repo, worker):
    subject = case["subject"]
    difficulty = case["difficulty"]
    items = case["items"]
    filename = case["filename"]
    
    logger.info(f"Submitting test case: {subject} | {difficulty} | Items: {items}")
    
    # Create the job
    job = await job_repo.create(subject=subject, difficulty=difficulty, items_requested=items)
    job_id = job["id"]
    
    # Enqueue the job
    await worker.enqueue_job(job_id)
    
    # Poll until completed or failed
    logger.info(f"Polling job {job_id}...")
    while True:
        job_record = await job_repo.get_by_id(job_id)
        status = job_record["status"]
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            logger.info(f"Job {job_id} finished with status: {status.value}")
            if status == JobStatus.FAILED:
                logger.error(f"Job {job_id} failed with error: {job_record['error_message']}")
            break
        await asyncio.sleep(2.0)
        
    # Retrieve final results and events
    job_record = await job_repo.get_by_id(job_id)
    generated_items = await item_repo.get_items_by_job_id(job_id)
    events = await event_repo.get_events_by_job_id(job_id)
    
    # Calculate Latency & Performance Metrics
    metrics = calculate_job_metrics(job_record, generated_items, events)
    
    output_data = {
        "job": {
            "id": job_record["id"],
            "subject": job_record["subject"],
            "difficulty": job_record["difficulty"],
            "items_requested": job_record["items_requested"],
            "status": job_record["status"].value,
            "total_cost": job_record["total_cost"],
            "created_at": str(job_record["created_at"]),
            "completed_at": str(job_record["updated_at"])
        },
        "metrics": metrics,
        "items": [
            {
                "id": it["id"],
                "question": it["question"],
                "choices": it["choices"],
                "correct_answer": it["correct_answer"],
                "explanation": it["explanation"],
                "cost": it["cost"],
                "status": it["status"].value,
                "attempts": it["attempts"]
            }
            for it in generated_items
        ]
    }
    
    # Ensure test_cases directory exists
    os.makedirs("test_cases", exist_ok=True)
    
    output_path = os.path.join("test_cases", filename)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
        
    logger.info(f"Saved results to {output_path}")

async def main():
    # 1. Initialize DB
    await init_db()
    
    # 2. Instantiate repos
    job_repo = SQLAlchemyJobRepository(async_session_factory)
    item_repo = SQLAlchemyItemRepository(async_session_factory)
    event_repo = SQLAlchemyEventRepository(async_session_factory)
    
    # 3. Instantiate providers
    # Use OpenAI by default, fallback to OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key and not gemini_key:
        logger.error("No LLM API keys found! Please set OPENAI_API_KEY or GEMINI_API_KEY in your environment.")
        return
        
    primary_provider = OpenAIProvider()
    if gemini_key:
        fallback_provider = GeminiProvider()
    else:
        fallback_provider = OpenAIProvider()
        
    # 4. Instantiate orchestrator
    orchestrator = PipelineOrchestrator(
        job_repo=job_repo,
        item_repo=item_repo,
        event_repo=event_repo,
        primary_provider=primary_provider,
        fallback_provider=fallback_provider
    )
    
    # 5. Start Worker
    worker = BackgroundQueueWorker(job_repo=job_repo, orchestrator=orchestrator)
    await worker.start()
    
    try:
        # Run cases sequentially to avoid exceeding rate limits
        for case in TEST_CASES:
            await run_test_case(case, job_repo, item_repo, event_repo, worker)
    finally:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
