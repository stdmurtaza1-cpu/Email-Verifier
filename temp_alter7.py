import re
import os

# 1. Update middleware/auth.py
path_auth = "d:/Quantx/Email Verifier/middleware/auth.py"
with open(path_auth, "r", encoding="utf-8") as f:
    auth_content = f.read()

# Add hashlib import if needed
if "import hashlib" not in auth_content:
    auth_content = "import hashlib\n" + auth_content

# Update X-API-Key validation
target_validation = """    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        user = db.query(User).filter(User.api_key == api_key_header).first()"""
replacement_validation = """    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        hashed_incoming = hashlib.sha256(api_key_header.encode()).hexdigest()
        user = db.query(User).filter(User.api_key == hashed_incoming).first()"""
auth_content = auth_content.replace(target_validation, replacement_validation)

target_link = """        partner = db.query(User).filter(User.api_key == user.linked_api_key).first()"""
replace_link = """        # If user.linked_api_key is stored RAW, hash it here. But if it's already stored as hash when linking, query directly.
        # Assuming linked_api_key might be the raw key provided by the user during link, we hash it:
        linked_hash = hashlib.sha256(user.linked_api_key.encode()).hexdigest()
        partner = db.query(User).filter(User.api_key == linked_hash).first()"""
auth_content = auth_content.replace(target_link, replace_link)

with open(path_auth, "w", encoding="utf-8") as f:
    f.write(auth_content)

# 2. Update routes/api.py to include POST /api/keys
path_api = "d:/Quantx/Email Verifier/routes/api.py"
with open(path_api, "r", encoding="utf-8") as f:
    api_content = f.read()

if "import secrets" not in api_content:
    api_content = "import secrets\nimport hashlib\n" + api_content

new_endpoint = """
@router.post("/keys")
async def generate_api_key(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    raw_key = "evs_" + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    
    current_user.api_key = hashed
    current_user.api_key_active = True
    db.commit()
    
    return {
        "api_key": raw_key,
        "message": "Save this key now. It will never be shown again."
    }
"""
if "@router.post(\"/keys\")" not in api_content:
    # insert before @router.post("/verify")
    api_content = api_content.replace('@router.post("/verify")', new_endpoint + '\n@router.post("/verify")')

# Also fix GET /api/me so it doesn't expose the hash verbatim as the API key to the frontend dashboard 
# It would confuse users.
target_me_return = """    return {
        "email": current_user.email,
        "plan": current_user.plan,
        "credits": current_user.credits,
        "api_key": current_user.api_key,
        "partner_status": current_user.partner_status,
        "partner_daily_limit": current_user.partner_daily_limit,
        "partner_credits_used_today": current_user.partner_credits_used_today,
    }"""
replace_me_return = """    return {
        "email": current_user.email,
        "plan": current_user.plan,
        "credits": current_user.credits,
        "api_key": "evs_••••••••••••••••••••••••",  # Hashed on backend
        "partner_status": current_user.partner_status,
        "partner_daily_limit": current_user.partner_daily_limit,
        "partner_credits_used_today": current_user.partner_credits_used_today,
    }"""
api_content = api_content.replace(target_me_return, replace_me_return)

with open(path_api, "w", encoding="utf-8") as f:
    f.write(api_content)

# 3. Update Auth to generate secure hashes on signup
path_reg = "d:/Quantx/Email Verifier/routes/auth.py"
with open(path_reg, "r", encoding="utf-8") as f:
    reg_content = f.read()

if "import secrets" not in reg_content:
    reg_content = "import secrets\nimport hashlib\n" + reg_content

target_user = """    import uuid
    new_user = User(
        email=data.email, 
        password_hash=pending["password_hash"], 
        credits=100, 
        api_key=str(uuid.uuid4())
    )"""

replace_user = """    raw_key = "evs_" + secrets.token_urlsafe(32)
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    
    new_user = User(
        email=data.email, 
        password_hash=pending["password_hash"], 
        credits=100, 
        api_key=hashed_key
    )"""
reg_content = reg_content.replace(target_user, replace_user)

with open(path_reg, "w", encoding="utf-8") as f:
    f.write(reg_content)

# 4. Create the migration script 
migration_script = """import os
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
"""
with open("d:/Quantx/Email Verifier/migrate_api_keys.py", "w", encoding="utf-8") as f:
    f.write(migration_script)

print("Backend configured.")
