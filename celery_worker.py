import asyncio
import csv
import os
import logging
from datetime import datetime
from typing import Optional

from celery import Celery
from celery.utils.log import get_task_logger
from core.verifier import verify_email
from celery.signals import worker_process_init
import threading
import core.worker_registry as worker_registry

logger = get_task_logger(__name__)

@worker_process_init.connect
def init_celery_identity(**kwargs):
    def run_heartbeat():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(worker_registry.start_worker_heartbeat("celery"))
        
    t = threading.Thread(target=run_heartbeat, daemon=True)
    t.start()
    logger.info("Celery Worker Identity registered and Heartbeat engaged.")

# ── Celery app ────────────────────────────────────────────────────────────────
redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
celery_app = Celery(
    "email_verifier",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,   # prevents memory hogs with large batches
    worker_concurrency=4,           # safe default; override via --concurrency CLI flag
    task_track_started=True,
    task_acks_late=True,            # re-queue task if worker dies mid-flight
    worker_lost_wait=10,
)

# ── Helpers ───────────────────────────────────────────────────────────────────
BULK_CHUNK_SIZE = 100
BULK_CONCURRENCY = 50
JOBS_DIR = os.path.join(os.path.dirname(__file__), "uploads", "jobs")


def _ensure_jobs_dir():
    os.makedirs(JOBS_DIR, exist_ok=True)


def _cache_update(job_id: str, data: dict, ttl: int = 86400):
    """Synchronous Redis hash update — used inside Celery tasks (no async loop)."""
    try:
        import redis as _redis
        r = _redis.from_url(redis_url, decode_responses=True)
        r.hset(f"job:{job_id}", mapping={str(k): str(v) for k, v in data.items()})
        r.expire(f"job:{job_id}", ttl)
    except Exception as exc:
        logger.warning(f"Redis update failed for job {job_id}: {exc}")


def _build_email_result_obj(r: dict, user_id: int, file_id: Optional[int]):
    """Build an EmailResult ORM object without importing at module level."""
    from database import EmailResult
    return EmailResult(
        user_id=user_id,
        file_id=file_id,
        email=r.get("email", ""),
        status=r.get("status", "UNKNOWN"),
        score=int(r.get("quality_score", 0) or 0),
        syntax_valid=bool(r.get("syntax", False)),
        is_disposable=bool(r.get("disposable", False)),
        mx_found=bool(r.get("mx", False)),
        smtp_response=None,
        used_proxy=r.get("used_proxy"),
        verified_at=datetime.utcnow(),
    )


def _flush_to_db(rows: list, batch_size: int = 100):
    """Persist a list of EmailResult objects to the DB in batches."""
    if not rows:
        return
    from database import SessionLocal
    db = SessionLocal()
    try:
        for i in range(0, len(rows), batch_size):
            db.bulk_save_objects(rows[i : i + batch_size])
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"DB flush error: {exc}")
    finally:
        db.close()


# ── Bulk-job Celery task (COORDINATOR) ──────────────────────────────────────────
@celery_app.task(
    bind=True,
    name="process_bulk_job",
    max_retries=0,
    time_limit=600,
)
def process_bulk_job(
    self,
    job_id: str,
    emails: list,
    user_id: int,
    file_id: Optional[int] = None,
):
    """
    Celery task: Coordinates a large list of emails by chunking them and dispatching to chunk_queue.
    """
    _ensure_jobs_dir()
    total = len(emails)
    
    _cache_update(job_id, {"status": "processing", "processed": 0, "total": total, "chunks_total": (total + BULK_CHUNK_SIZE - 1) // BULK_CHUNK_SIZE, "chunks_completed": 0})

    try:
        from database import SessionLocal, UserFile
        db = SessionLocal()
        try:
            uf = db.query(UserFile).filter(UserFile.id == file_id).first() if file_id else None
            if uf:
                uf.status = "processing"
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Could not update UserFile to processing: {exc}")

    # Dispatch chunks
    chunk_index = 0
    for start in range(0, total, BULK_CHUNK_SIZE):
        chunk = emails[start : start + BULK_CHUNK_SIZE]
        process_bulk_chunk.apply_async(
            args=[job_id, chunk, user_id, file_id, chunk_index, total],
            queue="chunk_queue"
        )
        chunk_index += 1

    logger.info(f"[{job_id}] Coordinator dispatched {chunk_index} chunks.")
    return {"job_id": job_id, "total": total, "status": "dispatching"}

@celery_app.task(
    bind=True,
    name="process_bulk_chunk",
    max_retries=15,
    time_limit=1800,
)
def process_bulk_chunk(
    self,
    job_id: str,
    chunk_emails: list,
    user_id: int,
    file_id: Optional[int],
    chunk_index: int,
    total_emails: int
):
    def _is_cancelled(job_id: str) -> bool:
        try:
            import redis as _redis
            r = _redis.from_url(redis_url, decode_responses=True)
            job_data = r.hgetall(f"job:{job_id}")
            return job_data.get("status") == "cancelled"
        except Exception:
            return False

    if _is_cancelled(job_id):
        logger.info(f"[{job_id}] Chunk {chunk_index} cancelled.")
        return

    results_container = []
    
    async def _run_chunk():
        sem = asyncio.Semaphore(BULK_CONCURRENCY)
        async def bounded(email: str):
            async with sem:
                return await verify_email(email)

        res = await asyncio.gather(*[bounded(e) for e in chunk_emails], return_exceptions=True)
        results_container.extend(res)
        
    asyncio.run(_run_chunk())

    db_rows = []
    failed_rows = []
    requeue_emails = []
    
    for email_str, r in zip(chunk_emails, results_container):
        if not isinstance(r, Exception):
            status = r.get("status", "UNKNOWN")
            if status in ["GREYLISTED", "TIMEOUT", "CONNECTION_REFUSED", "UNVERIFIABLE"]:
                requeue_emails.append(email_str)
                failed_rows.append(_build_email_result_obj(r, user_id, file_id))
            else:
                db_rows.append(_build_email_result_obj(r, user_id, file_id))
        else:
            logger.error(f"Error in chunk for {email_str}: {r}")
            requeue_emails.append(email_str)
            r_mock = {"email": email_str, "status": "UNKNOWN", "details": str(r)}
            failed_rows.append(_build_email_result_obj(r_mock, user_id, file_id))

    _flush_to_db(db_rows)

    try:
        import redis as _redis
        r = _redis.from_url(redis_url, decode_responses=True)
        if db_rows:
            r.hincrby(f"job:{job_id}", "processed", len(db_rows))
    except Exception as e:
        logger.error(f"[{job_id}] Redis update failed in chunk: {e}")

    if requeue_emails:
        if self.request.retries < self.max_retries:
            logger.info(f"[{job_id}] Retrying {len(requeue_emails)} emails in chunk {chunk_index} (Attempt {self.request.retries + 1}/{self.max_retries})")
            retry_delay = 300 * (self.request.retries + 1)
            raise self.retry(
                args=[job_id, requeue_emails, user_id, file_id, chunk_index, total_emails],
                countdown=retry_delay
            )
        else:
            logger.warning(f"[{job_id}] Max retries reached for chunk {chunk_index}. Saving {len(failed_rows)} temporary failures as final.")
            _flush_to_db(failed_rows)
            try:
                import redis as _redis
                r = _redis.from_url(redis_url, decode_responses=True)
                r.hincrby(f"job:{job_id}", "processed", len(failed_rows))
            except Exception as e:
                pass

    try:
        import redis as _redis
        r = _redis.from_url(redis_url, decode_responses=True)
        chunks_done = r.hincrby(f"job:{job_id}", "chunks_completed", 1)
        chunks_total = int(r.hget(f"job:{job_id}", "chunks_total") or 0)
        
        if chunks_done >= chunks_total and chunks_total > 0:
            finalize_bulk_job.apply_async(args=[job_id, file_id, total_emails], queue="coordinator_queue")
    except Exception as e:
        logger.error(f"[{job_id}] Redis chunks update failed: {e}")

@celery_app.task(name="finalize_bulk_job")
def finalize_bulk_job(job_id: str, file_id: Optional[int], total_emails: int):
    # We will generate the CSV from the DB here
    _cache_update(job_id, {"status": "completed", "processed": total_emails})
    
    try:
        from database import SessionLocal, UserFile, EmailResult
        db = SessionLocal()
        try:
            # Optionally write CSV here
            results_path = os.path.join(JOBS_DIR, f"{job_id}.csv")
            with open(results_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "email", "status", "quality_score",
                    "syntax", "mx", "smtp", "catch_all",
                    "disposable", "role", "details"
                ])
                
                results = db.query(EmailResult).filter(EmailResult.file_id == file_id).all() if file_id else []
                for r in results:
                    writer.writerow([
                        r.email, r.status, r.score, r.syntax_valid, r.mx_found, 
                        bool(r.smtp_response), False, r.is_disposable, False, r.smtp_response
                    ])
            
            uf = db.query(UserFile).filter(UserFile.id == file_id).first() if file_id else None
            if uf:
                uf.status = "completed"
                uf.processed_count = total_emails
                uf.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Could not finalize UserFile {file_id}: {exc}")
        
    logger.info(f"[{job_id}] Bulk job finalized — {total_emails} emails.")


# ── Original small-batch tasks (kept intact) ──────────────────────────────────
@celery_app.task(name="verify_single_email")
def verify_single_email(email: str):
    """Background wrapper for a single email verification."""
    logger.info(f"Processing single email: {email}")
    return asyncio.run(verify_email(email))


@celery_app.task(bind=True, name="verify_batch_emails", max_retries=3)
def verify_batch_emails(self, emails: list, completed_results: list = None):
    """
    Background wrapper for bulk email verification grouping.
    Handles 50-100 items per task, with greylisted-email retry logic.
    """
    completed_results = completed_results or []
    logger.info(f"Processing batch of {len(emails)} emails (Task ID: {self.request.id})")

    async def process():
        sem = asyncio.Semaphore(50)

        async def bounded_verify(e):
            async with sem:
                return await verify_email(e)

        tasks = [bounded_verify(e) for e in emails]
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(process())

    newly_completed = []
    greylisted_emails = []

    for email_address, r in zip(emails, results):
        if isinstance(r, Exception):
            logger.error(f"Email processed: {email_address} | Status: ERROR | Error: {str(r)}")
            newly_completed.append({
                "email": email_address,
                "status": "ERROR",
                "details": str(r),
                "quality_score": 0,
                "verification_method": "error",
            })
        else:
            status = r.get("status")
            details = r.get("details", "")
            logger.info(f"Email processed: {email_address} | Status: {status} | Details: {details}")

            if status == "GREYLISTED":
                greylisted_emails.append(email_address)
            else:
                newly_completed.append(r)

    all_completed = completed_results + newly_completed

    if greylisted_emails:
        logger.warning(f"Found {len(greylisted_emails)} GREYLISTED emails. Retrying in 20 minutes...")
        raise self.retry(
            args=[greylisted_emails],
            kwargs={"completed_results": all_completed},
            countdown=1200,
        )

    logger.info(f"Batch completed successfully. Total processed: {len(all_completed)}")
    return all_completed
