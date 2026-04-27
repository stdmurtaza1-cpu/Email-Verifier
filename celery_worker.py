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


# ── Bulk-job Celery task ──────────────────────────────────────────────────────
@celery_app.task(
    bind=True,
    name="process_bulk_job",
    max_retries=0,          # don't auto-retry — jobs can be massive
    time_limit=7200,        # hard kill after 2 hrs
    soft_time_limit=6900,   # SoftTimeLimitExceeded raised 5 min before hard kill
)
def process_bulk_job(
    self,
    job_id: str,
    emails: list,
    user_id: int,
    file_id: Optional[int] = None,
):
    """
    Celery task: verifies a large list of emails, writes a CSV result file,
    persists every result to email_results, and updates user_files + Redis cache.

    Dispatched by POST /api/bulk-verify-large.
    Progress tracked in Redis hash  job:{job_id}.
    """
    _ensure_jobs_dir()

    total = len(emails)
    results_path = os.path.join(JOBS_DIR, f"{job_id}.csv")

    # Mark as processing
    _cache_update(job_id, {"status": "processing", "processed": 0, "total": total})

    # Update UserFile status
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

    # Removed isolated _run_chunk because we consolidate into a single asyncio.run

    def _is_paused(job_id: str) -> bool:
        """Check if this job has been paused via Redis flag."""
        try:
            import redis as _redis
            r = _redis.from_url(redis_url, decode_responses=True)
            return r.get(f"job:{job_id}:paused") == "1"
        except Exception:
            return False

    def _is_cancelled(job_id: str) -> bool:
        """Check if this job has been cancelled."""
        try:
            import redis as _redis
            r = _redis.from_url(redis_url, decode_responses=True)
            job_data = r.hgetall(f"job:{job_id}")
            return job_data.get("status") == "cancelled"
        except Exception:
            return False

    async def _run_all() -> None:
        try:
            with open(results_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "email", "status", "quality_score",
                    "syntax", "mx", "smtp", "catch_all",
                    "disposable", "role", "spf", "dmarc", "details",
                ])

                processed = 0
                sem = asyncio.Semaphore(BULK_CONCURRENCY)

                async def bounded(email: str):
                    async with sem:
                        return await verify_email(email)

                for start in range(0, total, BULK_CHUNK_SIZE):
                    # Check for pause: wait until resumed
                    while _is_paused(job_id):
                        _cache_update(job_id, {"status": "paused", "processed": processed})
                        await asyncio.sleep(3)
                        if _is_cancelled(job_id):
                            break

                    # Check for cancellation
                    if _is_cancelled(job_id):
                        _cache_update(job_id, {"status": "cancelled", "processed": processed})
                        logger.info(f"[{job_id}] Job cancelled by user.")
                        return {"job_id": job_id, "total": total, "status": "cancelled"}

                    # Resume status
                    _cache_update(job_id, {"status": "processing", "processed": processed})

                    chunk = emails[start : start + BULK_CHUNK_SIZE]
                    results = await asyncio.gather(*[bounded(e) for e in chunk], return_exceptions=True)

                    db_rows = []
                    for r in results:
                        if isinstance(r, Exception):
                            writer.writerow(["", "ERROR", 0, False, False,
                                             False, False, False, False, False, False, str(r)])
                        else:
                            writer.writerow([
                                r.get("email", ""),
                                r.get("status", ""),
                                r.get("quality_score", 0),
                                r.get("syntax", False),
                                r.get("mx", False),
                                r.get("smtp", False),
                                r.get("catch_all", False),
                                r.get("disposable", False),
                                r.get("role", False),
                                r.get("spf", False),
                                r.get("dmarc", False),
                                r.get("details", ""),
                            ])
                            db_rows.append(_build_email_result_obj(r, user_id, file_id))

                    # Persist this chunk to DB (sync flush is okay in background worker)
                    _flush_to_db(db_rows)

                    processed += len(chunk)
                    _cache_update(job_id, {"status": "processing", "processed": processed})
                    logger.info(f"[{job_id}] {processed}/{total} processed")

        except Exception as exc:
            raise exc

    try:
        # Run the entire processing block in ONE event loop to prevent redis_pool errors
        # across multiple loop instantiations.
        loop_result = asyncio.run(_run_all())
        if loop_result and loop_result.get("status") == "cancelled":
            return loop_result


        # ── Job complete ──────────────────────────────────────────────────────
        _cache_update(job_id, {"status": "completed", "processed": total})

        try:
            from database import SessionLocal, UserFile
            db = SessionLocal()
            try:
                uf = db.query(UserFile).filter(UserFile.id == file_id).first() if file_id else None
                if uf:
                    uf.status = "completed"
                    uf.processed_count = total
                    uf.completed_at = datetime.utcnow()
                    db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning(f"Could not update UserFile to completed: {exc}")

        logger.info(f"[{job_id}] Bulk job finished — {total} emails.")
        return {"job_id": job_id, "total": total, "status": "completed"}

    except Exception as exc:
        logger.error(f"[{job_id}] Bulk job FAILED: {exc}", exc_info=True)
        _cache_update(job_id, {"status": "failed", "error": str(exc)})

        try:
            from database import SessionLocal, UserFile
            db = SessionLocal()
            try:
                uf = db.query(UserFile).filter(UserFile.id == file_id).first() if file_id else None
                if uf:
                    uf.status = "failed"
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass

        raise  # let Celery mark task as FAILURE


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
