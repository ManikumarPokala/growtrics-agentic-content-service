import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.repositories.database import init_db, async_session_factory
from app.repositories.job_repo import SQLAlchemyJobRepository
from app.repositories.item_repo import SQLAlchemyItemRepository
from app.repositories.event_repo import SQLAlchemyEventRepository
from app.providers.llm.openai import OpenAIProvider
from app.providers.llm.gemini import GeminiProvider
from app.application.orchestrator import PipelineOrchestrator
from app.workers.queue_worker import BackgroundQueueWorker
from app.api.routes import router as jobs_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("growtrics")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Database Tables and WAL Mode
    logger.info("Initializing database...")
    await init_db()

    # 2. Instantiate Repositories
    job_repo = SQLAlchemyJobRepository(async_session_factory)
    item_repo = SQLAlchemyItemRepository(async_session_factory)
    event_repo = SQLAlchemyEventRepository(async_session_factory)

    # 3. Instantiate LLM Providers
    primary_provider = OpenAIProvider()
    # If GEMINI_API_KEY is configured, use Gemini as fallback, otherwise fallback to another OpenAI instance or OpenAI fallback model
    if settings.GEMINI_API_KEY:
        fallback_provider = GeminiProvider()
    else:
        # Fallback to OpenAI using primary/fallback model
        fallback_provider = OpenAIProvider(model_name=settings.FALLBACK_MODEL)

    # 4. Instantiate Orchestrator
    orchestrator = PipelineOrchestrator(
        job_repo=job_repo,
        item_repo=item_repo,
        event_repo=event_repo,
        primary_provider=primary_provider,
        fallback_provider=fallback_provider
    )

    # 5. Instantiate and Start Background Queue Worker Pool
    queue_worker = BackgroundQueueWorker(job_repo=job_repo, orchestrator=orchestrator)
    logger.info("Starting background worker pool...")
    await queue_worker.start()

    # 6. Save resources to application state for route access
    app.state.job_repo = job_repo
    app.state.item_repo = item_repo
    app.state.event_repo = event_repo
    app.state.queue_worker = queue_worker

    yield

    # Shutdown: Stop worker pool gracefully
    logger.info("Stopping background worker pool...")
    await queue_worker.stop()

app = FastAPI(
    title="Growtrics Agentic Content Generation Service",
    description="FastAPI prototype of a reliable, cost-conscious multi-agent assessment generation backend.",
    version="1.0.0",
    lifespan=lifespan
)

# Register routes
app.include_router(jobs_router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Growtrics Agentic Content Generation Service",
        "version": "1.0.0"
    }
