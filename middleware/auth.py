import hashlib
from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from database import get_db, User
import os
from dotenv import load_dotenv

load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-mail-ninja-key-123")
ADMIN_SECRET_KEY = os.getenv("ADMIN_JWT_SECRET", "super_secret_admin_jwt_key_9999")
ALGORITHM = "HS256"

async def get_raw_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.email == email).first()
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    return user

async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 1. Check for X-API-Key explicitly
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        hashed_incoming = hashlib.sha256(api_key_header.encode()).hexdigest()
        user = db.query(User).filter(User.api_key == hashed_incoming).first()
        if user:
            if not getattr(user, "is_active", True) or not getattr(user, "api_key_active", True):
                raise HTTPException(status_code=403, detail="Account or API Key disabled.")
            return user
            
    # 2. Check for Bearer token fallback
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Provide Bearer token or X-API-Key.", headers={"WWW-Authenticate": "Bearer"})
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None: raise HTTPException(status_code=401, detail="Invalid token content")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
        
    user = db.query(User).filter(User.email == email).first()
    if user is None: raise HTTPException(status_code=401, detail="User not found")
    if not getattr(user, "is_active", True): raise HTTPException(status_code=403, detail="Account disabled.")
    
    # [LICENSE SHARING INTERCEPT]
    if getattr(user, "linked_api_key", None) and getattr(user, "partner_status", None) == "approved":
        # If user.linked_api_key is stored RAW, hash it here. But if it's already stored as hash when linking, query directly.
        # Assuming linked_api_key might be the raw key provided by the user during link, we hash it:
        linked_hash = hashlib.sha256(user.linked_api_key.encode()).hexdigest()
        partner = db.query(User).filter(User.api_key == linked_hash).first()
        if partner and getattr(partner, "is_active", True) and getattr(partner, "api_key_active", True):
            partner.is_linked_session = True
            partner.original_email = user.email
            partner.original_id = user.id
            partner.original_api_key = user.api_key
            partner.child_user_obj = user  # Preserve the actual user object for daily limit enforcement
            return partner

    return user

async def get_current_admin(
    request: Request,
    token: str = Depends(oauth2_scheme)
):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        payload = jwt.decode(token, ADMIN_SECRET_KEY, algorithms=[ALGORITHM])
        role: str = payload.get("role")
        if role != "admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate admin credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return {"role": "admin", "username": payload.get("sub")}
