import asyncio
import secrets
import hashlib
from cache import cache_hset, cache_hgetall, cache_set
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel
import re
import os
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db, SessionLocal, User, EmailResult, UserFile, PageContent
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

def track_user_analytics(user: User, amount: int) -> None:
    current_month_str = datetime.utcnow().strftime('%Y-%m')
    if getattr(user, 'current_month', None) != current_month_str:
        user.current_month = current_month_str
        user.monthly_verifications = 0
    if not user.total_verifications: user.total_verifications = 0
    if not user.monthly_verifications: user.monthly_verifications = 0
    
    user.total_verifications += amount
    user.monthly_verifications += amount

def check_and_deduct_credits(current_user: User, amount: int, db: Session = None) -> None:
    if hasattr(current_user, 'is_linked_session'):
        child = current_user.child_user_obj
        # Re-fetch with row lock to prevent race conditions under high traffic
        if db:
            child = db.query(User).filter(User.id == child.id).with_for_update().first()
            current_user_locked = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        else:
            current_user_locked = current_user
        today = date.today()
        # Safely compare: partner_limit_reset_date is a DateTime column (returns datetime),
        # while today is a date — always extract .date() before comparing to avoid
        # the datetime != date bug that caused the daily counter to always reset.
        reset_date = child.partner_limit_reset_date
        reset_day = reset_date.date() if hasattr(reset_date, 'date') else reset_date
        if reset_day != today:
            child.partner_credits_used_today = 0
            child.partner_limit_reset_date = today

        if child.partner_credits_used_today + amount > child.partner_daily_limit:
            rem = max(0, child.partner_daily_limit - child.partner_credits_used_today)
            raise HTTPException(status_code=403, detail=f"Partner daily limit reached. You can use {rem} more today.")

        if current_user_locked.credits < amount:
            raise HTTPException(status_code=403, detail="Partner has insufficient credits.")

        child.partner_credits_used_today += amount
        child.partner_credits_used_lifetime = (child.partner_credits_used_lifetime or 0) + amount
        current_user_locked.credits -= amount

        track_user_analytics(child, amount)
        track_user_analytics(current_user_locked, amount)
    else:
        # Re-fetch with row lock to prevent race conditions under high traffic
        if db:
            locked_user = db.query(User).filter(User.id == current_user.id).with_for_update().first()
        else:
            locked_user = current_user
        if locked_user.credits < amount:
            raise HTTPException(status_code=403, detail=f"Insufficient credits. You have {locked_user.credits} but need {amount}.")
        locked_user.credits -= amount
        track_user_analytics(locked_user, amount)

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


def _ensure_jobs_dir():
    os.makedirs(JOBS_DIR, exist_ok=True)


def _build_email_result(r: dict, user_id: int, file_id: Optional[int] = None) -> EmailResult:
    """Convert a verify_email() result dict into an EmailResult ORM object."""
    return EmailResult(
        user_id=user_id,
        file_id=file_id,
        email=r.get("email", ""),
        status=r.get("status", "UNKNOWN"),
        score=int(r.get("quality_score", 0) or 0),
        syntax_valid=bool(r.get("syntax", False)),
        is_disposable=bool(r.get("disposable", False)),
        mx_found=bool(r.get("mx", False)),
        smtp_response=None,          # raw SMTP code not surfaced in result dict
        verified_at=datetime.utcnow(),
    )


def _bulk_save_results(db: Session, result_objects: list, batch_size: int = 100) -> None:
    """Insert EmailResult rows in batches to avoid large memory spikes."""
    for i in range(0, len(result_objects), batch_size):
        batch = result_objects[i : i + batch_size]
        db.bulk_save_objects(batch)
        db.commit()


# _process_bulk_job removed — logic now lives in celery_worker.process_bulk_job


class VerifyRequest(BaseModel):
    email: str

@router.post("/verify-free")
@limiter.limit("10/day")
async def verify_free(request: Request, payload: VerifyRequest, db: Session = Depends(get_db)):
    result = await verify_email(payload.email)

    # Persist result — best-effort (no user_id for anonymous free tier)
    try:
        db.add(_build_email_result(result, user_id=0, file_id=None))
        db.commit()
    except Exception:
        db.rollback()  # don't block the response

    return result


@router.post("/keys")
async def generate_api_key(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    raw_key = "evs_" + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    
    current_user.api_key = hashed
    current_user.api_key_active = True
    db.commit()
    
    return {
        "api_key": raw_key,
        "message": "Save this key now. It will never be shown again."
    }

@router.post("/verify")
@limiter.limit("300/minute")
async def verify_single(request: Request, payload: VerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_and_deduct_credits(current_user, 1, db)
    db.commit()

    result = await verify_email(payload.email)

    # Persist result
    try:
        user_id = getattr(current_user, 'original_id', current_user.id)
        db.add(_build_email_result(result, user_id=user_id, file_id=None))
        db.commit()
    except Exception:
        db.rollback()

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
    email_pattern = r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}"
    emails = list(set(re.findall(email_pattern, text)))
                
    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found in the provided data.")
        
    if len(emails) > 2000:
        raise HTTPException(status_code=400, detail="For more than 2000 emails use POST /api/bulk-verify-large with a file. Max 1 million.")
        
    check_and_deduct_credits(current_user, len(emails), db)
    db.commit()

    # Process concurrently using the custom engine with connection limits
    sem = asyncio.Semaphore(50)
    
    async def bounded_verify(email):
        async with sem:
            return await verify_email(email)
            
    tasks = [bounded_verify(email) for email in emails]
    results = await asyncio.gather(*tasks)

    # Persist all results in batches of 100
    try:
        user_id = getattr(current_user, 'original_id', current_user.id)
        rows = [_build_email_result(r, user_id=user_id, file_id=None) for r in results if not isinstance(r, Exception)]
        _bulk_save_results(db, rows, batch_size=100)
    except Exception:
        db.rollback()
    
    return {
        "results": results,
        "total": len(results),
        "credits_used": len(results),
        "credits_remaining": get_display_credits(current_user)
    }


@router.post("/bulk-verify-large")
async def verify_bulk_large(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk verify up to 1M emails via Celery. Returns job_id immediately; poll /bulk-verify/status/{job_id}."""
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

    email_pattern = r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}"
    emails = list(dict.fromkeys(re.findall(email_pattern, text)))[:BULK_MAX_EMAILS]

    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found.")

    check_and_deduct_credits(current_user, len(emails), db)
    db.commit()

    user_id = getattr(current_user, 'original_id', current_user.id)

    # Create UserFile tracking row (history + admin stats)
    user_file = UserFile(
        user_id=user_id,
        filename=file.filename or "bulk_upload",
        file_size=size,
        file_type="csv",
        status="queued",
        processed_count=0,
    )
    try:
        db.add(user_file)
        db.commit()
        db.refresh(user_file)
        file_id: Optional[int] = user_file.id
    except Exception:
        db.rollback()
        file_id = None

    job_id = str(uuid.uuid4())
    _ensure_jobs_dir()

    # Register job in Redis BEFORE dispatching to Celery
    await cache_hset(f"job:{job_id}", {
        "status": "queued",
        "total": len(emails),
        "processed": 0,
        "error": "",
        "user_id": user_id,
        "file_id": file_id or "",
        "created_at": datetime.utcnow().isoformat(),
    }, ttl=86400)

    # Dispatch to Celery — crash-safe, survives web server restarts
    try:
        from celery_worker import process_bulk_job
        process_bulk_job.delay(job_id, emails, user_id, file_id)
    except Exception as exc:
        # Refund credits and surface the error if Celery is down
        current_user.credits += len(emails)
        db.commit()
        await cache_hset(f"job:{job_id}", {"status": "failed", "error": str(exc)}, ttl=3600)
        raise HTTPException(
            status_code=503,
            detail=f"Celery worker unavailable. Ensure Redis + celery-worker service are running. ({exc})"
        )

    return {
        "job_id": job_id,
        "status": "queued",
        "total": len(emails),
        "message": "Job queued. Poll GET /api/bulk-verify/status/{job_id} for progress, then GET /api/bulk-verify/download/{job_id} to download CSV.",
        "credits_remaining": get_display_credits(current_user),
    }


@router.get("/bulk-verify/status/{job_id}")
async def bulk_job_status(job_id: str, current_user: User = Depends(get_current_user)):
    job = await cache_hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    if str(job.get("user_id")) != str(true_user_id):
        raise HTTPException(status_code=403, detail="Not your job.")
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "total": int(job.get("total", 0)),
        "processed": int(job.get("processed", 0)),
        "progress_pct": round(100 * float(job["processed"]) / float(job["total"]), 1) if float(job.get("total", 0)) else 0,
        "download_ready": job["status"] == "completed",
        "error": job.get("error"),
    }


@router.get("/bulk-verify/download/{job_id}")
async def bulk_job_download(job_id: str, current_user: User = Depends(get_current_user)):
    job = await cache_hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    if str(job.get("user_id")) != str(true_user_id):
        raise HTTPException(status_code=403, detail="Not your job.")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not ready for download. Check status first.")
    path = os.path.join(JOBS_DIR, f"{job_id}.csv")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Result file not found.")
    return FileResponse(path, filename=f"verified_{job_id}.csv", media_type="text/csv")


@router.post("/bulk-verify/pause/{job_id}")
async def bulk_job_pause(job_id: str, current_user: User = Depends(get_current_user)):
    """Pause a running bulk job. The job will finish the current chunk then wait."""
    job = await cache_hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    if str(job.get("user_id")) != str(true_user_id):
        raise HTTPException(status_code=403, detail="Not your job.")
    if job.get("status") not in ("processing", "queued"):
        raise HTTPException(status_code=400, detail=f"Job cannot be paused in status: {job.get('status')}")
    await cache_set(f"job:{job_id}:paused", "1", ttl=86400)
    return {"job_id": job_id, "action": "paused"}


@router.post("/bulk-verify/resume/{job_id}")
async def bulk_job_resume(job_id: str, current_user: User = Depends(get_current_user)):
    """Resume a paused bulk job."""
    job = await cache_hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    if str(job.get("user_id")) != str(true_user_id):
        raise HTTPException(status_code=403, detail="Not your job.")
    await cache_set(f"job:{job_id}:paused", "0", ttl=86400)
    return {"job_id": job_id, "action": "resumed"}


class BatchVerifyRequest(BaseModel):
    emails: list[str]

@router.post("/verify-batch")
async def verify_batch(request: Request, payload: BatchVerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Limit batch size to 5 as requested
    emails = payload.emails[:5]
    
    check_and_deduct_credits(current_user, len(emails), db)
    db.commit()

    tasks = [verify_email(email) for email in emails]
    results = await asyncio.gather(*tasks)

    # Persist results
    try:
        user_id = getattr(current_user, 'original_id', current_user.id)
        rows = [_build_email_result(r, user_id=user_id, file_id=None) for r in results if not isinstance(r, Exception)]
        _bulk_save_results(db, rows, batch_size=100)
    except Exception:
        db.rollback()
    
    return {
        "results": results,
        "credits_remaining": get_display_credits(current_user)
    }

@router.post("/verify-batch-async")
async def verify_batch_async(request: Request, payload: BatchVerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_and_deduct_credits(current_user, len(payload.emails), db)
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

@router.get("/page/{slug}")
async def get_page_content(slug: str, db: Session = Depends(get_db)):
    page_content = db.query(PageContent).filter(PageContent.page_slug == slug).first()
    if not page_content:
        return {"slug": slug, "html_content": ""}
    return {"slug": slug, "html_content": page_content.html_content}
