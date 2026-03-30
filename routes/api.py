from fastapi import APIRouter, Depends, HTTPException, Security, Request, UploadFile, File, Form, Body, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel
import re
import os
import uuid
from sqlalchemy.orm import Session
from database import get_db, User
from middleware.auth import get_current_user
from core.verifier import verify_email
import csv
import io
from slowapi import Limiter
from slowapi.util import get_remote_address
from celery.result import AsyncResult, GroupResult
from celery import group
from datetime import date

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

def check_and_deduct_credits(current_user: User, amount: int) -> None:
    if hasattr(current_user, 'is_linked_session'):
        child = current_user.child_user_obj
        today = date.today()
        if child.partner_limit_reset_date != today:
            child.partner_credits_used_today = 0
            child.partner_limit_reset_date = today
            
        if child.partner_credits_used_today + amount > child.partner_daily_limit:
            rem = max(0, child.partner_daily_limit - child.partner_credits_used_today)
            raise HTTPException(status_code=403, detail=f"Partner daily limit reached. You can use {rem} more today.")
            
        if current_user.credits < amount:
            raise HTTPException(status_code=403, detail="Partner has insufficient credits.")
            
        child.partner_credits_used_today += amount
        current_user.credits -= amount
    else:
        if current_user.credits < amount:
            raise HTTPException(status_code=403, detail=f"Insufficient credits. You have {current_user.credits} but need {amount}.")
        current_user.credits -= amount

def get_display_credits(current_user: User) -> int:
    if hasattr(current_user, 'is_linked_session'):
        child = current_user.child_user_obj
        return max(0, child.partner_daily_limit - child.partner_credits_used_today)
    return current_user.credits

# --- Bulk (1M+) job config ---
BULK_MAX_EMAILS = 1_000_000
BULK_CHUNK_SIZE = 2000
BULK_CONCURRENCY = 50
BULK_MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
JOBS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "jobs")

_bulk_jobs: dict[str, dict] = {}  # job_id -> { status, total, processed, results_path, error, user_id }


def _ensure_jobs_dir():
    os.makedirs(JOBS_DIR, exist_ok=True)


async def _process_bulk_job(job_id: str, emails: list[str]):
    _ensure_jobs_dir()
    job = _bulk_jobs.get(job_id)
    if not job or job["status"] != "processing":
        return
    total = len(emails)
    results_path = os.path.join(JOBS_DIR, f"{job_id}.csv")
    sem = asyncio.Semaphore(BULK_CONCURRENCY)

    async def bounded_verify(email: str):
        async with sem:
            return await verify_email(email)

    try:
        with open(results_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["email", "status", "score", "syntax", "mx", "smtp", "catch_all", "disposable", "role", "spf", "dmarc", "details"])
            processed = 0
            for start in range(0, total, BULK_CHUNK_SIZE):
                chunk = emails[start : start + BULK_CHUNK_SIZE]
                tasks = [bounded_verify(e) for e in chunk]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        row = ["", "ERROR", 0, False, False, False, False, False, False, False, False, str(r)]
                    else:
                        row = [
                            r.get("email", ""),
                            r.get("status", ""),
                            r.get("score", 0),
                            r.get("syntax", False),
                            r.get("mx", False),
                            r.get("smtp", False),
                            r.get("catch_all", False),
                            r.get("disposable", False),
                            r.get("role", False),
                            r.get("spf", False),
                            r.get("dmarc", False),
                            (r.get("details") or ""),
                        ]
                    writer.writerow(row)
                processed += len(chunk)
                job["processed"] = processed
                job["status"] = "processing"
        job["status"] = "completed"
        job["processed"] = total
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    return


class VerifyRequest(BaseModel):
    email: str

@router.post("/verify-free")
@limiter.limit("10/day")
async def verify_free(request: Request, payload: VerifyRequest):
    result = await verify_email(payload.email)
    return result

@router.post("/verify")
async def verify_single(request: Request, payload: VerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_and_deduct_credits(current_user, 1)
    db.commit()

    result = await verify_email(payload.email)
    
    result["credits_remaining"] = get_display_credits(current_user)
    return result

@router.post("/bulk-verify")
async def verify_bulk(request: Request, file: Optional[UploadFile] = File(None), raw_text: Optional[str] = Form(None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = ""
    if file and file.filename:
        content = await file.read()
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid file encoding. Please upload a UTF-8 file (.csv or .txt).")
    elif raw_text:
        text = raw_text
    else:
        raise HTTPException(status_code=400, detail="No file or text provided for bulk verification.")
        
    # Extract emails using regex across the entire parsed text
    email_pattern = r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
    emails = list(set(re.findall(email_pattern, text)))
                
    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found in the provided data.")
        
    if len(emails) > 2000:
        raise HTTPException(status_code=400, detail="For more than 2000 emails use POST /api/bulk-verify-large with a file. Max 1 million.")
        
    check_and_deduct_credits(current_user, len(emails))
    db.commit()
        
    # Process concurrently using the custom engine with connection limits
    sem = asyncio.Semaphore(50)
    
    async def bounded_verify(email):
        async with sem:
            return await verify_email(email)
            
    tasks = [bounded_verify(email) for email in emails]
    results = await asyncio.gather(*tasks)
    
    return {
        "results": results,
        "total": len(results),
        "credits_used": len(results),
        "credits_remaining": get_display_credits(current_user)
    }


@router.post("/bulk-verify-large")
async def verify_bulk_large(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk verify up to 1M emails via background job. Returns job_id; poll status and download CSV when done."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
    size = 0
    chunks = []
    while True:
        chunk = await file.read(512 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > BULK_MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail=f"File too large. Max {BULK_MAX_FILE_BYTES // (1024*1024)} MB.")
        chunks.append(chunk)
    try:
        text = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid encoding. Use UTF-8.")

    email_pattern = r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
    emails = list(dict.fromkeys(re.findall(email_pattern, text)))[:BULK_MAX_EMAILS]

    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found.")
        
    check_and_deduct_credits(current_user, len(emails))
    db.commit()

    job_id = str(uuid.uuid4())
    _ensure_jobs_dir()
    _bulk_jobs[job_id] = {
        "status": "processing",
        "total": len(emails),
        "processed": 0,
        "results_path": None,
        "error": None,
        "user_id": getattr(current_user, 'original_id', current_user.id),
    }

    background_tasks.add_task(_process_bulk_job, job_id, emails)
    return {
        "job_id": job_id,
        "total": len(emails),
        "message": "Bulk verification started. Use GET /api/bulk-verify/status/{job_id} to poll progress, then GET /api/bulk-verify/download/{job_id} to download CSV.",
        "credits_remaining": get_display_credits(current_user),
    }


@router.get("/bulk-verify/status/{job_id}")
async def bulk_job_status(job_id: str, current_user: User = Depends(get_current_user)):
    job = _bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    if job.get("user_id") != true_user_id:
        raise HTTPException(status_code=403, detail="Not your job.")
    return {
        "job_id": job_id,
        "status": job["status"],
        "total": job["total"],
        "processed": job["processed"],
        "progress_pct": round(100 * job["processed"] / job["total"], 1) if job["total"] else 0,
        "download_ready": job["status"] == "completed",
        "error": job.get("error"),
    }


@router.get("/bulk-verify/download/{job_id}")
async def bulk_job_download(job_id: str, current_user: User = Depends(get_current_user)):
    job = _bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    if job.get("user_id") != true_user_id:
        raise HTTPException(status_code=403, detail="Not your job.")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not ready for download. Check status first.")
    path = os.path.join(JOBS_DIR, f"{job_id}.csv")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Result file not found.")
    return FileResponse(path, filename=f"verified_{job_id}.csv", media_type="text/csv")


class BatchVerifyRequest(BaseModel):
    emails: list[str]

@router.post("/verify-batch")
async def verify_batch(request: Request, payload: BatchVerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Limit batch size to 5 as requested
    emails = payload.emails[:5]
    
    check_and_deduct_credits(current_user, len(emails))
    db.commit()
    
    tasks = [verify_email(email) for email in emails]
    results = await asyncio.gather(*tasks)
    
    return {
        "results": results,
        "credits_remaining": get_display_credits(current_user)
    }

@router.post("/verify-batch-async")
async def verify_batch_async(request: Request, payload: BatchVerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_and_deduct_credits(current_user, len(payload.emails))
    db.commit()

    # Dispatch to Celery Queue with Chunking
    try:
        from celery_worker import verify_batch_emails, celery_app
        
        chunk_size = 100
        emails = payload.emails
        chunks = [emails[i:i + chunk_size] for i in range(0, len(emails), chunk_size)]
        
        if len(chunks) == 1:
            task = verify_batch_emails.delay(chunks[0])
            task_id = task.id
        else:
            job = group(verify_batch_emails.s(chunk) for chunk in chunks)
            result = job.apply_async()
            result.save()
            task_id = result.id
            
    except Exception as e:
        # Refund credits if celery fails to dispatch
        current_user.credits += len(payload.emails)
        if hasattr(current_user, "is_linked_session"):
            current_user.child_user_obj.partner_credits_used_today -= len(payload.emails)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to dispatch to Celery. Ensure Redis is running: {str(e)}")

    return {
        "task_id": task_id,
        "message": "Batch processing started in background.",
        "total_queued": len(payload.emails),
        "chunks": len(chunks),
        "credits_remaining": get_display_credits(current_user)
    }

@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str, current_user: User = Depends(get_current_user)):
    try:
        from celery_worker import celery_app
    except ImportError:
        raise HTTPException(status_code=500, detail="Celery worker not configured properly.")
        
    # Attempt to restore as GroupResult first
    group_result = GroupResult.restore(task_id, app=celery_app)
    if group_result:
        completed = group_result.completed_count()
        total = len(group_result)
        if group_result.ready():
            results = []
            for res_list in group_result.join():
                if isinstance(res_list, list):
                    results.extend(res_list)
            return {"task_id": task_id, "status": "completed", "results": results}
        else:
            return {"task_id": task_id, "status": "processing", "progress": f"{completed}/{total} chunks completed"}
        
    # Fallback to single AsyncResult lookup
    task_result = AsyncResult(task_id, app=celery_app)
    
    if task_result.state == 'PENDING':
        return {"task_id": task_id, "status": "pending"}
    elif task_result.state == 'SUCCESS':
        return {"task_id": task_id, "status": "completed", "results": task_result.result}
    elif task_result.state == 'RETRY':
        return {"task_id": task_id, "status": "retrying (greylisted delay limit reached)"}
    elif task_result.state == 'FAILURE':
        return {"task_id": task_id, "status": "failed", "error": str(task_result.info)}
    elif task_result.state == 'STARTED':
        return {"task_id": task_id, "status": "processing"}
    else:
        return {"task_id": task_id, "status": task_result.state.lower()}
