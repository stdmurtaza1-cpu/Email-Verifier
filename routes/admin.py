from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db, User, Subscription, EmailResult
from middleware.auth import get_current_admin
from pydantic import BaseModel
import os
from datetime import datetime, date, timedelta
import uuid

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

@router.post("/upgrade-plan")
async def upgrade_user_plan(data: UpgradePlanDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.email == data.user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    plan = data.plan.lower()
    
    if plan == 'free':
        user.credits = 100
    elif plan == 'starter':
        user.credits = 100000
    elif plan == 'pro':
        user.credits = 150000
    elif plan == 'enterprise':
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
            "api_key": getattr(u, "api_key", None)
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
