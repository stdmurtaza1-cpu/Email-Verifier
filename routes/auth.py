import secrets
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional
from database import get_db, User
from middleware.auth import get_current_user, get_raw_current_user
from pydantic import BaseModel
import os
import bcrypt
from slowapi import Limiter
from slowapi.util import get_remote_address
import random
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

limiter = Limiter(key_func=get_remote_address)

_pending_signups = {}  # In-memory dict as requested. For multi-worker production, Redis is recommended.
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "verify@yourdomain.com")

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-mail-ninja-key-123")
ADMIN_SECRET_KEY = os.getenv("ADMIN_JWT_SECRET", "super_secret_admin_jwt_key_9999")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "SecurePassword123!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week
ADMIN_TOKEN_EXPIRE_MINUTES = 60 * 8 # 8 hours

class UserAuthDTO(BaseModel):
    email: str
    password: str

class LinkKeyDTO(BaseModel):
    partner_key: str

class Token(BaseModel):
    access_token: str
    token_type: str

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register")
@limiter.limit("10/hour")
async def register(request: Request, user_data: UserAuthDTO, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    otp = str(random.randint(100000, 999999))
    hashed_password = get_password_hash(user_data.password)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    _pending_signups[user_data.email] = {
        "otp": otp,
        "password_hash": hashed_password,
        "expires_at": expires_at,
        "attempts": 0
    }
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333; text-align: center;">Welcome to Email Verifier Ninja!</h2>
        <p style="color: #555; font-size: 16px;">To complete your registration and receive your 100 free credits, please verify your email address.</p>
        <div style="text-align: center; margin: 30px 0;">
            <p style="font-size: 14px; color: #888; margin-bottom: 5px;">Your Verification Code</p>
            <h1 style="color: #4A90E2; letter-spacing: 5px; margin: 0;">{otp}</h1>
        </div>
        <p style="color: #888; font-size: 12px; text-align: center;">This code will expire in 10 minutes.</p>
    </div>
    """
    
    if SENDGRID_API_KEY:
        try:
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=user_data.email,
                subject='Your OTP for Email Verifier Ninja',
                html_content=html_content)
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            sg.send(message)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to send OTP email. Please try again.")
    else:
        print(f"DEV MODE - OTP for {user_data.email}: {otp}")
        
    return {"message": "OTP sent to your email", "email": user_data.email}

class OTPVerifyDTO(BaseModel):
    email: str
    otp: str

@router.post("/verify-otp", response_model=Token)
@limiter.limit("5/minute")
async def verify_otp(request: Request, data: OTPVerifyDTO, db: Session = Depends(get_db)):
    if data.email not in _pending_signups:
        raise HTTPException(status_code=400, detail="No pending registration found for this email.")
        
    pending = _pending_signups[data.email]
    
    if datetime.utcnow() > pending["expires_at"]:
        del _pending_signups[data.email]
        raise HTTPException(status_code=400, detail="OTP has expired. Please register again.")
        
    if pending["attempts"] >= 3:
        del _pending_signups[data.email]
        raise HTTPException(status_code=400, detail="Maximum OTP attempts exceeded. Please register again.")
        
    if pending["otp"] != data.otp:
        pending["attempts"] += 1
        raise HTTPException(status_code=400, detail=f"Invalid OTP. {3 - pending['attempts']} attempts remaining.")
        
    raw_key = "evs_" + secrets.token_urlsafe(32)
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    
    new_user = User(
        email=data.email, 
        password_hash=pending["password_hash"], 
        credits=100, 
        api_key=hashed_key
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    del _pending_signups[data.email]
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
@limiter.limit("20/minute")
async def login(request: Request, user_data: UserAuthDTO, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/link-key")
@limiter.limit("5/minute")
async def link_partner_key(request: Request, data: LinkKeyDTO, db: Session = Depends(get_db), current_user: User = Depends(get_raw_current_user)):
    user_to_update = db.query(User).filter(User.id == current_user.id).first()
    
    if not data.partner_key or not data.partner_key.strip():
        user_to_update.linked_api_key = None
        user_to_update.partner_status = None
        db.commit()
        return {"message": "Partner license unlinked successfully."}
        
    partner_key = data.partner_key.strip()
    partner = db.query(User).filter(User.api_key == partner_key).first()
    
    if not partner:
        raise HTTPException(status_code=404, detail="Partner API Key not found.")
    
    if partner.id == user_to_update.id:
        raise HTTPException(status_code=400, detail="Cannot link your own account key.")
        
    if not getattr(partner, "is_active", True) or not getattr(partner, "api_key_active", True):
        raise HTTPException(status_code=403, detail="Partner account is currently disabled.")
        
    user_to_update.linked_api_key = partner_key
    user_to_update.partner_status = "pending"
    db.commit()
    return {"message": "License link request sent! Waiting for partner approval."}

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    from datetime import date
    if hasattr(current_user, 'is_linked_session'):
        child = current_user.child_user_obj
        used_today = child.partner_credits_used_today if child.partner_limit_reset_date == date.today() else 0
        rem_credits = max(0, child.partner_daily_limit - used_today)
        return {
            "email": current_user.original_email,
            "plan": current_user.plan + " (Shared License)",
            "credits": rem_credits,
            "api_key": current_user.original_api_key,
            "partner_status": "approved",
            "partner_daily_limit": child.partner_daily_limit,
            "partner_credits_used_today": used_today
        }
    else:
        used_today = getattr(current_user, "partner_credits_used_today", 0) if getattr(current_user, "partner_limit_reset_date", None) == date.today() else 0
        return {
            "email": getattr(current_user, 'original_email', current_user.email),
            "plan": current_user.plan,
            "credits": current_user.credits,
            "api_key": getattr(current_user, 'original_api_key', current_user.api_key),
            "partner_status": getattr(current_user, "partner_status", None),
            "partner_daily_limit": getattr(current_user, "partner_daily_limit", None),
            "partner_credits_used_today": used_today
        }

class AdminAuthDTO(BaseModel):
    username: str
    password: str

@router.post("/admin-login")
@limiter.limit("5/15minute")
async def admin_login(request: Request, data: AdminAuthDTO):
    if data.username != ADMIN_USER or data.password != ADMIN_PASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )
        
    expire = datetime.utcnow() + timedelta(minutes=ADMIN_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": data.username,
        "role": "admin",
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, ADMIN_SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": encoded_jwt, "token_type": "bearer"}

class ForgotPasswordDTO(BaseModel):
    email: str

@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordDTO, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        import secrets
        import os
        from cache import cache_set
        token = secrets.token_urlsafe(32)
        await cache_set(f"reset:{token}", user.id, ttl=900)
        
        FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")
        reset_link = f"{FRONTEND_URL}/reset-password.html?token={token}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px; text-align: center;">
            <h2 style="color: #333;">Reset Your Password</h2>
            <p style="color: #555; font-size: 16px;">We received a request to reset your password. Click the button below to set a new password.</p>
            <div style="margin: 30px 0;">
                <a href="{reset_link}" style="background-color: #4A90E2; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Reset Password</a>
            </div>
            <p style="color: #888; font-size: 12px;">This link expires in 15 minutes.</p>
            <p style="color: #888; font-size: 12px; margin-top: 20px;">If you didn't request this, you can safely ignore this email.</p>
        </div>
        """
        
        if SENDGRID_API_KEY:
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail
                message = Mail(
                    from_email=FROM_EMAIL,
                    to_emails=user.email,
                    subject='Password Reset - Email Verifier Ninja',
                    html_content=html_content)
                sg = SendGridAPIClient(SENDGRID_API_KEY)
                sg.send(message)
            except Exception as e:
                print(f"Failed to send reset email: {e}")
        else:
            print(f"DEV MODE - Reset link for {user.email}: {reset_link}")

    return {"message": "If this email is registered, a reset link has been sent."}

class ResetPasswordDTO(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordDTO, db: Session = Depends(get_db)):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        
    from cache import cache_get, cache_delete
    user_id = await cache_get(f"reset:{data.token}")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
        
    user.password_hash = get_password_hash(data.new_password)
    db.commit()
    
    await cache_delete(f"reset:{data.token}")
    
    return {"message": "Password updated. Please login with your new password."}
