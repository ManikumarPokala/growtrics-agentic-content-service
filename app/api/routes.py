import hashlib
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, status
from app.domain.entities import JobStatus
from app.api.schemas import JobCreateRequest, JobResponse, JobDetailsResponse, GeneratedItemResponse, JobMetricsResponse
from app.telemetry.metrics import calculate_job_metrics

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

def _generate_request_hash(req: JobCreateRequest) -> str:
    # Normalize inputs
    norm_subject = req.subject.strip().lower()
    norm_difficulty = req.difficulty.strip().lower()
    payload_str = f"{norm_subject}:{norm_difficulty}:{req.items_requested}"
    return hashlib.md5(payload_str.encode("utf-8")).hexdigest()

@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_generation_job(
    request: Request,
    payload: JobCreateRequest,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key")
):
    job_repo = request.app.state.job_repo
    worker = request.app.state.queue_worker
    
    # 1. Calculate Request Hash
    req_hash = _generate_request_hash(payload)

    # 2. Check Idempotency Key
    if x_idempotency_key:
        existing_job = await job_repo.get_by_idempotency_key(x_idempotency_key)
        if existing_job:
            # If job is cancelled or failed, we allow submitting it again. Otherwise, return existing.
            if existing_job["status"] not in (JobStatus.FAILED, JobStatus.CANCELLED):
                return existing_job

    # 3. Check Duplicate Request Hash (within past 2 hours to allow eventual re-runs)
    existing_hash_job = await job_repo.get_by_request_hash(req_hash)
    if existing_hash_job:
        if existing_hash_job["status"] not in (JobStatus.FAILED, JobStatus.CANCELLED):
            return existing_hash_job

    # 4. Create New Job Record
    job = await job_repo.create(
        subject=payload.subject,
        difficulty=payload.difficulty,
        items_requested=payload.items_requested,
        idempotency_key=x_idempotency_key,
        request_hash=req_hash
    )
    
    # 5. Enqueue Job in background worker
    await worker.enqueue_job(job["id"])
    
    # Refresh to get updated status (QUEUED)
    job_record = await job_repo.get_by_id(job["id"])
    return job_record

@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(request: Request, job_id: str):
    job_repo = request.app.state.job_repo
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Job with ID {job_id} not found."
        )
    return job

@router.get("/{job_id}/results", response_model=JobDetailsResponse)
async def get_job_results(request: Request, job_id: str):
    job_repo = request.app.state.job_repo
    item_repo = request.app.state.item_repo
    event_repo = request.app.state.event_repo
    
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Job with ID {job_id} not found."
        )
        
    items = await item_repo.get_items_by_job_id(job_id)
    events = await event_repo.get_events_by_job_id(job_id)
    
    # Calculate Latency & Performance Metrics (P50, P95, Failures, etc.)
    metrics = calculate_job_metrics(job, items, events)
    
    return {
        "job": job,
        "metrics": metrics,
        "items": items
    }
