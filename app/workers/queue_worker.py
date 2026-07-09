import asyncio
import datetime
import logging
from typing import List
from app.core.config import settings
from app.domain.entities import JobStatus
from app.domain.interfaces import JobRepository
from app.application.orchestrator import PipelineOrchestrator

logger = logging.getLogger("growtrics.worker")

class BackgroundQueueWorker:
    def __init__(self, job_repo: JobRepository, orchestrator: PipelineOrchestrator):
        self.job_repo = job_repo
        self.orchestrator = orchestrator
        self.queue = asyncio.Queue()
        self.worker_tasks: List[asyncio.Task] = []
        self._running = False

    async def enqueue_job(self, job_id: str) -> None:
        """Enqueues a job_id for execution."""
        await self.queue.put(job_id)
        # Mark as queued in the database
        await self.job_repo.update_status(job_id, JobStatus.QUEUED)
        logger.info(f"Enqueued Job ID: {job_id}")

    async def _worker_loop(self, worker_id: int) -> None:
        """Single worker task pulling jobs from the queue."""
        logger.info(f"Worker {worker_id} started.")
        while self._running:
            try:
                # Wait for next job
                job_id = await self.queue.get()
                logger.info(f"Worker {worker_id} picked up Job {job_id}")
                
                # Execute the job orchestration
                await self.orchestrator.execute_job(job_id)
                
                # Notify queue that task is processed
                self.queue.task_done()
                logger.info(f"Worker {worker_id} completed Job {job_id}")
                
            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelling...")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error while executing job: {str(e)}", exc_info=True)

    async def start(self) -> None:
        """Starts the worker pool and runs the crash recovery check."""
        self._running = True
        
        # 1. Run recovery manager for crashed/stuck jobs
        await self.run_crash_recovery()

        # 2. Spawn worker tasks
        for i in range(settings.WORKER_POOL_SIZE):
            task = asyncio.create_task(self._worker_loop(i))
            self.worker_tasks.append(task)

    async def stop(self) -> None:
        """Stops the worker pool gracefully."""
        self._running = False
        for task in self.worker_tasks:
            task.cancel()
        
        # Wait for all tasks to cancel
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()
        logger.info("Worker pool stopped.")

    async def run_crash_recovery(self) -> None:
        """
        Scans DB for stuck or uncompleted jobs. 
        Resets and re-queues them.
        """
        logger.info("Running crash recovery manager...")
        uncompleted_jobs = await self.job_repo.get_uncompleted_jobs()
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        
        for job in uncompleted_jobs:
            job_id = job["id"]
            status = job["status"]
            updated_at = job["updated_at"]
            
            # Calculate how long since the last heartbeat
            idle_delta = (now - updated_at).total_seconds()
            
            # If state is PENDING or QUEUED, re-queue immediately.
            # If state is PROCESSING and heartbeat is older than timeout, re-queue.
            should_requeue = (
                status in (JobStatus.PENDING, JobStatus.QUEUED) or
                (status == JobStatus.PROCESSING and idle_delta > settings.HEARTBEAT_TIMEOUT_SECONDS)
            )
            
            if should_requeue:
                logger.warning(
                    f"Crash Recovery: Job {job_id} is stuck in {status.value} (idle {idle_delta:.1f}s). Re-queuing..."
                )
                await self.enqueue_job(job_id)
