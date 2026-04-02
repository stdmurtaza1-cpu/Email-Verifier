import os
import sys

# Ensure we can import from database
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal, User

def run_migration():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            # We must preserve unique constraint on api_key, so we append unique tracker
            user.api_key = user.api_key + "_expired" 
            user.api_key_active = False
        db.commit()
        print(f"Successfully disabled API keys for {len(users)} users.")
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
