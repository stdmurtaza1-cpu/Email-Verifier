from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db, User
from middleware.auth import get_current_user
from pydantic import BaseModel
from datetime import date
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

class ApproveRequest(BaseModel):
    user_id: int
    daily_limit: int

class RejectRequest(BaseModel):
    user_id: int

@router.get("/requests")
async def get_partner_requests(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get users who have requested to link to this user's API key
    if hasattr(current_user, "is_linked_session"):
        return [] # Linked users cannot approve others
        
    requests = db.query(User).filter(
        User.linked_api_key == current_user.api_key,
        User.partner_status == "pending"
    ).all()
    
    return [
        {
            "id": r.id,
            "email": r.email,
            "date": r.created_at.isoformat()
        } for r in requests
    ]

@router.get("/users")
async def get_partner_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if hasattr(current_user, "is_linked_session"):
        return []
        
    users = db.query(User).filter(
        User.linked_api_key == current_user.api_key,
        User.partner_status == "approved"
    ).all()
    
    today = date.today()
    
    res = []
    for u in users:
        # Check if usage needs to be reset for display
        used_today = u.partner_credits_used_today
        if u.partner_limit_reset_date != today:
            used_today = 0
            
        res.append({
            "id": u.id,
            "email": u.email,
            "daily_limit": u.partner_daily_limit,
            "used_today": used_today
        })
    return res

@router.post("/approve")
@limiter.limit("20/minute")
async def approve_request(request: Request, data: ApproveRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if hasattr(current_user, "is_linked_session"):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user = db.query(User).filter(
        User.id == data.user_id,
        User.linked_api_key == current_user.api_key,
        User.partner_status == "pending"
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Request not found")
        
    user.partner_status = "approved"
    user.partner_daily_limit = data.daily_limit
    user.partner_credits_used_today = 0
    user.partner_limit_reset_date = date.today()
    
    db.commit()
    return {"message": "User approved successfully"}

@router.post("/reject")
@limiter.limit("20/minute")
async def reject_request(request: Request, data: RejectRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if hasattr(current_user, "is_linked_session"):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user = db.query(User).filter(
        User.id == data.user_id,
        User.linked_api_key == current_user.api_key
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.linked_api_key = None
    user.partner_status = None
    user.partner_daily_limit = None
    db.commit()
    return {"message": "User removed successfully"}

@router.put("/update-limit")
@limiter.limit("20/minute")
async def update_limit(request: Request, data: ApproveRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if hasattr(current_user, "is_linked_session"):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user = db.query(User).filter(
        User.id == data.user_id,
        User.linked_api_key == current_user.api_key,
        User.partner_status == "approved"
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Approved user not found")
        
    user.partner_daily_limit = data.daily_limit
    db.commit()
    return {"message": "Limit updated successfully"}

@router.delete("/remove/{user_id}")
async def remove_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if hasattr(current_user, "is_linked_session"):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user = db.query(User).filter(
        User.id == user_id,
        User.linked_api_key == current_user.api_key
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.linked_api_key = None
    user.partner_status = None
    user.partner_daily_limit = None
    db.commit()
    return {"message": "User access revoked"}
