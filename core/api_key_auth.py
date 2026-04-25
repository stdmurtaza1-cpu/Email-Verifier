import hashlib
from fastapi import Header, HTTPException, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db, ApiKey, ApiAnalytics, User
from cache import get_redis
import time
from datetime import datetime

async def log_api_usage(key_id: int, endpoint: str, status_code: int):
    from database import SessionLocal
    db = SessionLocal()
    try:
        analytics = ApiAnalytics(
            key_id=key_id,
            endpoint=endpoint,
            status_code=status_code,
            timestamp=datetime.utcnow()
        )
        db.add(analytics)
        db.commit()
    except Exception as e:
        db.rollback()
    finally:
        db.close()

async def get_api_key(
    request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
) -> User:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key header missing")

    hashed_key = hashlib.sha256(x_api_key.encode()).hexdigest()

    # Find the key in DB
    api_key_obj = db.query(ApiKey).filter(ApiKey.key == hashed_key).first()
    
    if not api_key_obj:
        raise HTTPException(status_code=401, detail="Invalid API Key")
        
    if api_key_obj.status != "active":
        raise HTTPException(status_code=403, detail="API Key has been revoked")

    # Rate Limiting via Redis
    try:
        r = get_redis()
        current_minute = int(time.time() / 60)
        limit_key = f"rate_limit:api_key:{api_key_obj.id}:{current_minute}"
        
        current_requests = await r.incr(limit_key)
        if current_requests == 1:
            await r.expire(limit_key, 60) # Expire after 1 minute
            
        if current_requests > api_key_obj.rate_limit:
            # Log as 429
            background_tasks.add_task(log_api_usage, db, api_key_obj.id, request.url.path, 429)
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Limit is {api_key_obj.rate_limit} requests per minute.")
    except HTTPException:
        raise
    except Exception as e:
        # If Redis fails, allow the request but maybe log
        pass

    # Log successful request
    # Note: we log 200 optimistically. If the endpoint itself fails, the endpoint logic would need to update this, 
    # but for typical usage tracking, just logging the hit is standard.
    background_tasks.add_task(log_api_usage, db, api_key_obj.id, request.url.path, 200)

    # Attach the ApiKey to the user object temporarily for downstream use
    user = api_key_obj.user
    user.used_api_key = api_key_obj
    return user
