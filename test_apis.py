import asyncio
from database import SessionLocal, User
from middleware.auth import get_current_user
from routes.auth import read_users_me
from routes.api import get_display_credits
from routes.storage import get_files, get_usage
from unittest.mock import MagicMock
from datetime import date

async def test_api():
    db = SessionLocal()
    
    # 1. Fetch a linked user to test if it's there
    child = db.query(User).filter(User.partner_status == "approved").first()
    if not child:
        print("No approved linked user found in DB. Let's create one!")
        # Find any two users or create them
        p = db.query(User).first()
        if not p:
            p = User(email="partner@test.com", password_hash="hash", credits=5000)
            db.add(p)
            db.commit()
            db.refresh(p)
        c = User(email="child@test.com", password_hash="hash", credits=0, 
                 linked_api_key=p.api_key, partner_status="approved", partner_daily_limit=100)
        db.add(c)
        db.commit()
        db.refresh(c)
        child = c
        partner = p
    else:
        partner = db.query(User).filter(User.api_key == child.linked_api_key).first()
        
    print(f"Child: {child.email}, Partner: {partner.email}")
    
    # 2. Simulate middleware intercept
    partner.is_linked_session = True
    partner.original_email = child.email
    partner.original_id = child.id
    partner.original_api_key = child.api_key
    partner.child_user_obj = child
    
    # 3. Test /api/me
    print("\n--- Testing /api/me ---")
    try:
        me_res = await read_users_me(partner)
        print("API ME Response:", me_res)
    except Exception as e:
        print("Error in /api/me:", e)
        
    # 4. Test missing credits math
    print("\n--- Testing API credits compute ---")
    try:
        creds = get_display_credits(partner)
        print("Disp Credits:", creds)
    except Exception as e:
        print("Error in display_credits:", e)
        
    # 5. Test Storage Usage
    print("\n--- Testing Storage Usage ---")
    try:
        usage = await get_usage(db=db, current_user=partner)
        print("Storage Usage:", usage)
    except Exception as e:
        import traceback
        traceback.print_exc()

    # 6. Test Get Files
    print("\n--- Testing Storage Files ---")
    try:
        files = await get_files(db=db, current_user=partner)
        print("Storage files count:", len(files))
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    db.close()

if __name__ == "__main__":
    asyncio.run(test_api())
