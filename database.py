from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import uuid

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("FATAL ERROR: DATABASE_URL environment variable is not set. Cannot connect to the database. Please set it in your .env file or environment.")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    plan = Column(String, default='free')
    credits = Column(Integer, default=100)
    api_key = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    is_active = Column(Boolean, default=True)
    api_key_active = Column(Boolean, default=True)
    linked_api_key = Column(String, nullable=True)
    partner_status = Column(String, nullable=True)  # 'pending' or 'approved'
    partner_daily_limit = Column(Integer, nullable=True) # e.g. 500
    partner_credits_used_today = Column(Integer, default=0)
    partner_limit_reset_date = Column(DateTime, nullable=True)
    
    # User Verification Analytics Trackers
    total_verifications = Column(Integer, default=0)
    monthly_verifications = Column(Integer, default=0)
    current_month = Column(String, default=lambda: datetime.datetime.utcnow().strftime('%Y-%m'))
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user")
    files = relationship("UserFile", back_populates="user")

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan = Column(String, nullable=False)
    credits_limit = Column(Integer, nullable=False)
    start_date = Column(DateTime, default=datetime.datetime.utcnow)
    end_date = Column(DateTime)

    user = relationship("User", back_populates="subscriptions")

class UserFile(Base):
    __tablename__ = "user_files"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    pool_api_key = Column(String, index=True, nullable=True)
    filename = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String, default="csv")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(String, nullable=True)
    # Bulk-job tracking
    status = Column(String, default="pending")          # pending | processing | completed | failed
    processed_count = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="files")
    email_results = relationship("EmailResult", back_populates="user_file", cascade="all, delete-orphan")

class EmailResult(Base):
    __tablename__ = "email_results"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    file_id = Column(Integer, ForeignKey("user_files.id"), nullable=True, index=True)
    email = Column(String, index=True, nullable=False)
    status = Column(String, index=True)
    score = Column(Integer, default=0)
    syntax_valid = Column(Boolean, default=False)
    is_disposable = Column(Boolean, default=False)
    mx_found = Column(Boolean, default=False)
    smtp_response = Column(Integer, nullable=True)   # raw SMTP code when available
    verified_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", backref="email_results")
    user_file = relationship("UserFile", back_populates="email_results")

class SmtpIp(Base):
    __tablename__ = "smtp_ips"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ip_address = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="active") # active, frozen, cooldown
    health_score = Column(Integer, default=100)
    last_checked = Column(DateTime, default=datetime.datetime.utcnow)

class PageContent(Base):
    __tablename__ = "page_contents"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    page_slug = Column(String, unique=True, index=True, nullable=False) # e.g. home, pricing, contact, privacy
    html_content = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception:
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
