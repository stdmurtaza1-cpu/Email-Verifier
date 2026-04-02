import os
import csv
import io
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from database import get_db, UserFile, User
from middleware.auth import get_current_user

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_STORAGE_BYTES = 1073741824  # 1GB

class SaveResultRequest(BaseModel):
    filename: str
    results: list
    description: Optional[str] = ""

@router.post("/save-results")
async def save_results(req: SaveResultRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    pool_api_key = getattr(current_user, 'original_api_key', current_user.api_key)
    
    user_dir = os.path.join(UPLOAD_DIR, str(true_user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    # Calculate current usage for the entire pool
    user_files_db = db.query(UserFile).filter(
        or_(
            UserFile.pool_api_key == pool_api_key,
            and_(UserFile.pool_api_key == None, UserFile.user_id == current_user.id)
        )
    ).all()
    current_usage = sum(f.file_size for f in user_files_db)
    
    # Create CSV
    output = io.StringIO()
    if len(req.results) > 0:
        writer = csv.DictWriter(output, fieldnames=["email", "status", "details"])
        writer.writeheader()
        for r in req.results:
            row = {
                "email": r.get("email", ""),
                "status": r.get("status", ""),
                "details": r.get("details", "")
            }
            writer.writerow(row)
            
    csv_data = output.getvalue().encode('utf-8')
    file_size = len(csv_data)
    
    if current_usage + file_size > MAX_STORAGE_BYTES:
        raise HTTPException(status_code=400, detail="Storage limit exceeded (1GB)")
        
    safe_filename = req.filename.replace("/", "").replace("\\", "").replace("..", "")
    if not safe_filename.endswith(".csv"):
        safe_filename += ".csv"
        
    file_path = os.path.join(user_dir, safe_filename)
    
    # Check if file exists to overwrite or make unique
    if os.path.exists(file_path):
        safe_filename = f"{int(time.time())}_{safe_filename}"
        file_path = os.path.join(user_dir, safe_filename)
        
    with open(file_path, "wb") as f:
        f.write(csv_data)
        
    new_file = UserFile(
        user_id=true_user_id,
        pool_api_key=pool_api_key,
        filename=safe_filename,
        file_size=file_size,
        file_type="csv",
        description=req.description
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    
    return {
        "file_id": new_file.id,
        "filename": new_file.filename,
        "size": new_file.file_size,
        "storage_used": current_usage + file_size
    }

@router.get("/files")
async def get_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    files = db.query(UserFile).filter(UserFile.user_id == true_user_id).order_by(UserFile.created_at.desc()).all()
    res = []
    for f in files:
        res.append({
            "id": f.id,
            "filename": f.filename,
            "size": f.file_size,
            "date": f.created_at.isoformat(),
            "download_url": f"/api/storage/download/{f.id}"
        })
    return res

@router.get("/download/{file_id}")
async def download_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    user_file = db.query(UserFile).filter(UserFile.id == file_id, UserFile.user_id == true_user_id).first()
    if not user_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_path = os.path.join(UPLOAD_DIR, str(true_user_id), user_file.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File missing from disk")
        
    return FileResponse(file_path, media_type="text/csv", filename=user_file.filename)

@router.delete("/delete/{file_id}")
async def delete_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    true_user_id = getattr(current_user, 'original_id', current_user.id)
    user_file = db.query(UserFile).filter(UserFile.id == file_id, UserFile.user_id == true_user_id).first()
    if not user_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_path = os.path.join(UPLOAD_DIR, str(true_user_id), user_file.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        
    db.delete(user_file)
    db.commit()
    return {"status": "deleted"}

@router.get("/usage")
async def get_usage(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pool_api_key = getattr(current_user, 'original_api_key', current_user.api_key)
    
    files = db.query(UserFile).filter(
        or_(
            UserFile.pool_api_key == pool_api_key,
            and_(UserFile.pool_api_key == None, UserFile.user_id == current_user.id)
        )
    ).all()
    used_bytes = sum((f.file_size or 0) for f in files)
    perc = (used_bytes / MAX_STORAGE_BYTES) * 100
    return {
        "used_bytes": used_bytes,
        "total_bytes": MAX_STORAGE_BYTES,
        "percentage": float(f"{perc:.2f}")
    }
