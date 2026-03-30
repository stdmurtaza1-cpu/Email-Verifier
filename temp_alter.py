import sqlite3
import os

db_path = "api_keys.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1;")
        print("Added is_active")
    except Exception as e:
        print("Skipped is_active:", e)
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN api_key_active BOOLEAN DEFAULT 1;")
        print("Added api_key_active")
    except Exception as e:
        print("Skipped api_key_active:", e)
        
    conn.commit()
    conn.close()
