import asyncio
import os
from celery import Celery
from core.verifier import verify_email
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# Configure Celery with Redis broker and backend
redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
celery_app = Celery(
    "email_verifier",
    broker=redis_url,
    backend=redis_url
)

# High Concurrency & Stability Tuning
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1, # Perfect for batch grouping, prevents memory hogs
    worker_concurrency=10, # Allow 10 processes concurrently
    task_track_started=True
)

@celery_app.task(name="verify_single_email")
def verify_single_email(email: str):
    """
    Background wrapper for a single email verification
    """
    logger.info(f"Processing single email: {email}")
    return asyncio.run(verify_email(email))

@celery_app.task(bind=True, name="verify_batch_emails", max_retries=3)
def verify_batch_emails(self, emails: list, completed_results: list = None):
    """
    Background wrapper for bulk email verification grouping. Handles 50-100 items per task.
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
                "verification_method": "error"
            })
        else:
            status = r.get("status")
            details = r.get("details", "")
            logger.info(f"Email processed: {email_address} | Status: {status} | Error: None | Details: {details}")
            
            if status == "GREYLISTED":
                greylisted_emails.append(email_address)
            else:
                newly_completed.append(r)
                
    # Merge older completed retries with current completed
    all_completed = completed_results + newly_completed
    
    # Retry logic for GREYLISTED
    if greylisted_emails:
        logger.warning(f"Found {len(greylisted_emails)} GREYLISTED emails. Retrying in 20 minutes...")
        # Countdown 1200 seconds = 20 minutes
        # We pass 'completed_results' so we don't drop the ones that successfully completed!
        raise self.retry(args=[greylisted_emails], kwargs={"completed_results": all_completed}, countdown=1200)
        
    logger.info(f"Batch completed successfully. Total processed: {len(all_completed)}")
    return all_completed
