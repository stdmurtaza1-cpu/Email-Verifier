from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from database import get_db, User, Subscription
from middleware.auth import get_current_admin
from pydantic import BaseModel
import os
from datetime import datetime

router = APIRouter()

class UpgradePlanDTO(BaseModel):
    user_email: str
    plan: str

@router.post("/upgrade-plan")
async def upgrade_user_plan(data: UpgradePlanDTO, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    user = db.query(User).filter(User.email == data.user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    plan = data.plan.lower()
    
    if plan == 'free':
        user.credits = 100
    elif plan == 'starter':
        user.credits = 5000
    elif plan == 'pro':
        user.credits = 50000
    elif plan == 'enterprise':
        user.credits = 9999999
    else:
        raise HTTPException(status_code=400, detail="Invalid plan specified")
        
    user.plan = plan
    
    # Store standard subscription record
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
            "joined_date": u.created_at.isoformat(),
        })
    return {"users": user_list}

@router.get("/stats")
async def get_admin_stats(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    users_count = db.query(User).count()
    return {"total_users": users_count, "message": "More stats can be derived from logging verifications if a table is added in the future."}
