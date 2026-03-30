import sqlite3
import uuid

def fix_keys():
    try:
        conn = sqlite3.connect("api_keys.db")
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM users WHERE api_key IS NULL OR api_key = ''")
        rows = cur.fetchall()
        
        for row in rows:
            new_key = str(uuid.uuid4())
            cur.execute("UPDATE users SET api_key = ? WHERE id = ?", (new_key, row[0]))
            
        conn.commit()
        conn.close()
        print(f"Successfully fixed {len(rows)} users by assigning them new API keys.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_keys()
