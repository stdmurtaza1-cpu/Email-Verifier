from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db, User, Subscription, EmailResult, SmtpIp, PageContent
from middleware.auth import get_current_admin
from pydantic import BaseModel
from fastapi import UploadFile, File
import os
from datetime import datetime, date, timedelta
import uuid
from cache import cache_hset, cache_hgetall, cache_hdel, get_redis

router = APIRouter()

class UpgradePlanDTO(BaseModel):
    user_email: str
    plan: str

class AddCreditsDTO(BaseModel):
    user_email: str
    credits_to_add: int

class ToggleUserDTO(BaseModel):
    user_email: str
    is_active: bool

class ToggleKeyDTO(BaseModel):
    key_id: int
    is_active: bool

class RevokeKeyDTO(BaseModel):
    key_id: int

class AddIpDTO(BaseModel):
    ip_address: str
    status: str = "active"

@router.post("/upgrade-plan")
async def upgrade_user_plan(data: UpgradePlanDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.email == data.user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    plan = data.plan.lower()
    
    if plan == 'free':
        user.credits = 100
    elif plan == 'starter':
        user.credits = 50000
    elif plan == 'pro':
        user.credits = 100000
    elif plan == 'ultimate':
        user.credits = 500000
    else:
        raise HTTPException(status_code=400, detail="Invalid plan specified")
        
    user.plan = plan
    
    sub = Subscription(
        user_id=user.id,
        plan=plan,
        credits_limit=user.credits
    )
    db.add(sub)
    db.commit()
    db.refresh(user)
    
    return {
        "message": "Plan upgraded successfully",
        "email": user.email,
        "new_plan": user.plan,
        "credits_remaining": user.credits
    }

@router.post("/add-credits")
async def add_credits(data: AddCreditsDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.email == data.user_email).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    current_credits = user.credits if user.credits is not None else 0
    user.credits = current_credits + data.credits_to_add
    
    db.commit()
    return {"message": "Credits added", "new_total": user.credits}

@router.post("/toggle-user")
async def toggle_user(data: ToggleUserDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.email == data.user_email).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    user.is_active = data.is_active
    db.commit()
    return {"message": "User status updated", "is_active": user.is_active}

@router.get("/users")
async def get_all_users(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    users = db.query(User).all()
    user_list = []
    for u in users:
        user_list.append({
            "id": u.id,
            "email": u.email,
            "plan": u.plan,
            "credits": u.credits,
            "joined_date": u.created_at.isoformat() if getattr(u, "created_at", None) else None,
            "is_active": getattr(u, "is_active", True),
            "api_key": getattr(u, "api_key", None),
            "total_verifications": getattr(u, 'total_verifications', 0),
            "monthly_verifications": getattr(u, 'monthly_verifications', 0)
        })
    return {"users": user_list}

@router.get("/keys")
async def get_all_keys(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    users = db.query(User).filter(User.api_key.isnot(None)).all()
    key_list = [{"id": u.id, "email": u.email, "api_key": u.api_key, "is_active": getattr(u, "api_key_active", True)} for u in users]
    return {"keys": key_list}

@router.post("/toggle-key")
async def toggle_key(data: ToggleKeyDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == data.key_id).first()
    if not user: raise HTTPException(status_code=404, detail="Key (User) not found")
    user.api_key_active = data.is_active
    db.commit()
    return {"message": "Key status updated"}

@router.delete("/revoke-key")
async def revoke_key(data: RevokeKeyDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == data.key_id).first()
    if not user: raise HTTPException(status_code=404, detail="Key (User) not found")
    user.api_key_active = False 
    user.api_key = str(uuid.uuid4())
    db.commit()
    return {"message": "Key revoked (regenerated)"}

@router.get("/stats")
async def get_admin_stats(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    try:
        users_count = db.query(User).count()
        today = date.today()
        
        # 1. today_verifications
        today_verifications = db.query(EmailResult).filter(
            func.date(EmailResult.verified_at) == today
        ).count()
        
        # 3. total_verifications
        total_verifications = db.query(EmailResult).count()
        
        # 4. history (Last 7 days)
        seven_days_ago = today - timedelta(days=6)
        history_query = db.query(
            func.date(EmailResult.verified_at).label('date'),
            func.count(EmailResult.id).label('count')
        ).filter(
            func.date(EmailResult.verified_at) >= seven_days_ago
        ).group_by(
            func.date(EmailResult.verified_at)
        ).order_by(
            func.date(EmailResult.verified_at)
        ).all()
        
        # 5. status_breakdown
        status_query = db.query(
            EmailResult.status,
            func.count(EmailResult.id).label('count')
        ).group_by(EmailResult.status).all()
        
        status_breakdown = {status: count for status, count in status_query if status is not None}
        
        # Build chart data for the last 7 days mapping safely
        chart_labels = [(seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        date_counts = {str(row.date): row.count for row in history_query}
        chart_values = [date_counts.get(label, 0) for label in chart_labels]
        
        month_ago = today - timedelta(days=30)
        verifications_month = db.query(EmailResult).filter(
            func.date(EmailResult.verified_at) >= month_ago
        ).count()

        return {
            "today_verifications": today_verifications,
            "total_users": users_count,
            "total_verifications": total_verifications,
            "history": {
                "labels": chart_labels,
                "values": chart_values
            },
            "status_breakdown": status_breakdown,
            # Keeping original keys for frontend compatibility as requested
            "verifications_today": today_verifications,
            "verifications_month": verifications_month,
            "verifications_all_time": total_verifications,
            "chart_data": {
                "labels": chart_labels,
                "values": chart_values
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")

@router.post("/ips")
async def add_smtp_ip(data: AddIpDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    existing = db.query(SmtpIp).filter(SmtpIp.ip_address == data.ip_address).first()
    if existing:
        raise HTTPException(status_code=400, detail="IP address already exists")
        
    smtp_ip = SmtpIp(ip_address=data.ip_address, status=data.status)
    db.add(smtp_ip)
    db.commit()
    db.refresh(smtp_ip)
    
    if data.status == "active":
        await cache_hset("smtp:active_ips", {data.ip_address: smtp_ip.health_score})
        
    return {"message": "IP added successfully", "id": smtp_ip.id}

@router.get("/ips")
async def get_smtp_ips(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    ips = db.query(SmtpIp).all()
    active_in_redis = await cache_hgetall("smtp:active_ips") or {}
    
    return {"ips": [
        {
            "id": ip.id,
            "ip_address": ip.ip_address,
            "status": ip.status,
            "health_score": ip.health_score,
            "last_checked": ip.last_checked.isoformat() if ip.last_checked else None,
            "in_rotation": ip.ip_address in active_in_redis
        } for ip in ips
    ]}

@router.patch("/ips/{ip_id}/freeze")
async def freeze_smtp_ip(ip_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    ip = db.query(SmtpIp).filter(SmtpIp.id == ip_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
        
    ip.status = "frozen"
    db.commit()
    
    # Must remove from ANY assigned subset pools natively!
    r = get_redis()
    await cache_hdel("smtp:active_ips", ip.ip_address)
    
    active_workers = await r.smembers("active_workers")
    for worker in active_workers:
        await r.hdel(f"worker:{worker}:ips", ip.ip_address)
        
    return {"message": "IP frozen and removed from all active rotations"}

# ── Distributed Worker Cluster Administration ────────────────────────────────
@router.get("/workers")
async def list_active_workers(current_admin: dict = Depends(get_current_admin)):
    r = get_redis()
    active_workers = await r.smembers("active_workers")
    
    worker_data = []
    for worker in active_workers:
        is_alive = await r.exists(f"worker:{worker}:heartbeat")
        assigned_ips = await cache_hgetall(f"worker:{worker}:ips") or {}
        
        worker_data.append({
            "worker_name": worker,
            "status": "online" if is_alive else "offline",
            "assigned_ip_count": len(assigned_ips),
            "assigned_ips": list(assigned_ips.keys())
        })
        
    return {"workers": worker_data}

@router.post("/workers/{worker_name}/assign/{ip_address}")
async def assign_worker_ip(worker_name: str, ip_address: str, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    ip = db.query(SmtpIp).filter(SmtpIp.ip_address == ip_address).first()
    if not ip or ip.status != "active":
        raise HTTPException(status_code=400, detail="IP not found or not active")
        
    global_ips = await cache_hgetall("smtp:active_ips") or {}
    if ip_address not in global_ips:
        raise HTTPException(status_code=400, detail="IP must be present in the global cache pool to map to a specific worker.")
        
    score = global_ips[ip_address]
    r = get_redis()
    await cache_hset(f"worker:{worker_name}:ips", {ip_address: score})
    await r.hdel("smtp:active_ips", ip_address)
    
    logger.info(f"[MONITOR] EVENT=IP_ASSIGNED | worker={worker_name} | ip={ip_address} | msg=Strictly mapped IP to worker pool")
    return {"message": f"IP mapped securely. Strict allocation to {worker_name} applied."}

@router.post("/workers/{worker_name}/release/{ip_address}")
async def release_worker_ip(worker_name: str, ip_address: str, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    r = get_redis()
    worker_ips = await cache_hgetall(f"worker:{worker_name}:ips") or {}
    
    if ip_address not in worker_ips:
        raise HTTPException(status_code=404, detail="IP not assigned to that worker")
        
    score = worker_ips[ip_address]
    await cache_hset("smtp:active_ips", {ip_address: score})
    await r.hdel(f"worker:{worker_name}:ips", ip_address)
    
    logger.info(f"[MONITOR] EVENT=IP_RELEASED | worker={worker_name} | ip={ip_address} | msg=Released IP back to Master Gateway")
    return {"message": f"IP orphaned back to the Master Gateway globally mapped pool."}

@router.get("/stats")
async def get_system_stats(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    r = get_redis()
    
    # Global counts
    active_workers = await r.smembers("active_workers")
    global_ips = await cache_hgetall("smtp:active_ips") or {}
    total_active_ips = len(global_ips)
    
    for worker in active_workers:
        w_ips = await cache_hgetall(f"worker:{worker}:ips") or {}
        total_active_ips += len(w_ips)
        
    # Aggregate success metrics
    total_processed = 0
    total_successes = 0
    
    for worker in active_workers:
        w_proc = await r.get(f"worker:{worker}:processed")
        w_succ = await r.get(f"worker:{worker}:success")
        total_processed += int(w_proc) if w_proc else 0
        total_successes += int(w_succ) if w_succ else 0
        
    overall_success_rate = f"{int((total_successes/total_processed)*100)}%" if total_processed > 0 else "N/A"
    total_crashes = await r.get("system:worker_crashes") or 0
    
    return {
        "overview": {
            "total_workers_online": len(active_workers),
            "total_active_ips": total_active_ips,
            "overall_success_rate": overall_success_rate,
            "total_emails_processed_recently": total_processed,
            "total_worker_crashes": int(total_crashes)
        }
    }

@router.get("/test-smtp-ip/{ip}")
async def test_smtp_ip(ip: str, current_admin: dict = Depends(get_current_admin)):
    """Validates real-time external socket capability via standard port 25 constraints."""
    try:
        import socket
        s = socket.create_connection((ip, 25), timeout=5)
        response = s.recv(1024).decode('utf-8').strip()
        s.close()
        return {
            "ip": ip,
            "port_25_open": True,
            "response": response,
            "status": "healthy"
        }
    except Exception as e:
        return {
            "ip": ip,
            "port_25_open": False,
            "response": str(e),
            "status": "unhealthy"
        }

class PageContentDTO(BaseModel):
    html_content: str

@router.get("/page/{slug}")
async def get_admin_page_content(slug: str, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    page = db.query(PageContent).filter(PageContent.page_slug == slug).first()
    return {"slug": slug, "html_content": page.html_content if page else ""}

@router.post("/page/{slug}")
async def save_admin_page_content(slug: str, data: PageContentDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    page = db.query(PageContent).filter(PageContent.page_slug == slug).first()
    if not page:
        page = PageContent(page_slug=slug, html_content=data.html_content)
        db.add(page)
    else:
        page.html_content = data.html_content
    db.commit()
    return {"message": f"Page '{slug}' updated successfully."}

@router.post("/upload-image")
async def upload_admin_image(file: UploadFile = File(...), current_admin: dict = Depends(get_current_admin)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
    
    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    filename = f"{uuid.uuid4().hex}.{ext}"
    
    filepath = os.path.join("uploads", "images", filename)
    with open(filepath, "wb") as f:
        f.write(await file.read())
        
    return {"url": f"/uploads/images/{filename}"}
