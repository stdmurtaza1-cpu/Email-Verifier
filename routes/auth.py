import secrets
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

limiter = Limiter(key_func=get_remote_address)

_pending_signups = {}  # In-memory dict as requested. For multi-worker production, Redis is recommended.
_pending_resets = {}

SMTP_EMAIL = os.getenv("SMTP_EMAIL", "std.murtaza1@gmail.com").strip('"\'')
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "sceh mopw mvje wmhc").strip('"\'')
FROM_EMAIL = os.getenv("FROM_EMAIL", "std.murtaza1@gmail.com").strip('"\'')

def send_email_smtp(to_email: str, subject: str, html_content: str):
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        print(f"DEV MODE [No SMTP creds] - Email to {to_email} | Subject: {subject} | Content: {html_content}")
        return
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        
        part = MIMEText(html_content, "html")
        msg.attach(part)
        
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        raise e

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
async def register(request: Request, user_data: UserAuthDTO, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
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
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 30px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333; text-align: center;">VerifyNinja</h2>
        <p style="color: #555; text-align: center;">Your verification code is:</p>
        <div style="text-align: center; margin: 30px 0; padding: 20px; background: #f5f5f5; border-radius: 8px;">
            <span style="color: #4A90E2; font-size: 48px; font-weight: bold; letter-spacing: 8px;">
                {otp}
            </span>
        </div>
        <p style="color: #999; text-align: center; font-size: 13px;">This code expires in 10 minutes. Do not share this code with anyone.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #ccc; text-align: center; font-size: 11px;">VerifyNinja — Professional Email Validation</p>
    </div>
    """
    
    if True: # Always attempt to send email if not in pure dev mode
        background_tasks.add_task(send_email_smtp, user_data.email, 'VerifyNinja — Your OTP Code', html_content)
        
    return {"message": "OTP sent to your email", "email": user_data.email}

class OTPVerifyDTO(BaseModel):
    email: str
    otp: str

@router.post("/verify-otp", response_model=Token)
@limiter.limit("5/minute")
def verify_otp(request: Request, data: OTPVerifyDTO, db: Session = Depends(get_db)):
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
def login(request: Request, user_data: UserAuthDTO, db: Session = Depends(get_db)):
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
            "partner_credits_used_today": used_today,
            "total_verifications": getattr(child, "total_verifications", 0),
            "monthly_verifications": getattr(child, "monthly_verifications", 0)
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
            "partner_credits_used_today": used_today,
            "total_verifications": getattr(current_user, "total_verifications", 0),
            "monthly_verifications": getattr(current_user, "monthly_verifications", 0)
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
async def forgot_password(request: Request, data: ForgotPasswordDTO, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        otp = str(random.randint(100000, 999999))
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        _pending_resets[data.email] = {
            "otp": otp,
            "expires_at": expires_at,
            "attempts": 0
        }
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 30px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #333; text-align: center;">VerifyNinja Reset</h2>
            <p style="color: #555; text-align: center;">We received a request to reset your password. Here is your verification code:</p>
            <div style="text-align: center; margin: 30px 0; padding: 20px; background: #f5f5f5; border-radius: 8px;">
                <span style="color: #4A90E2; font-size: 48px; font-weight: bold; letter-spacing: 8px;">
                    {otp}
                </span>
            </div>
            <p style="color: #999; text-align: center; font-size: 13px;">This code expires in 10 minutes. If you didn't request this, you can safely ignore this email.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #ccc; text-align: center; font-size: 11px;">VerifyNinja — Professional Email Validation</p>
        </div>
        """
        
        if True:
            background_tasks.add_task(send_email_smtp, user.email, 'VerifyNinja — Password Reset OTP', html_content)

    return {"message": "If this email is registered, an OTP has been sent."}

class ResetPasswordDTO(BaseModel):
    email: str
    otp: str
    new_password: str

@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, data: ResetPasswordDTO, db: Session = Depends(get_db)):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        
    if data.email not in _pending_resets:
        raise HTTPException(status_code=400, detail="No pending password reset found for this email.")
        
    pending = _pending_resets[data.email]
    
    if datetime.utcnow() > pending["expires_at"]:
        del _pending_resets[data.email]
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
        
    if pending["attempts"] >= 3:
        del _pending_resets[data.email]
        raise HTTPException(status_code=400, detail="Maximum OTP attempts exceeded. Please try again.")
        
    if pending["otp"] != data.otp:
        pending["attempts"] += 1
        raise HTTPException(status_code=400, detail=f"Invalid OTP. {3 - pending['attempts']} attempts remaining.")
        
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
        
    user.password_hash = get_password_hash(data.new_password)
    db.commit()
    
    del _pending_resets[data.email]
    
    return {"message": "Password updated. Please login with your new password."}
