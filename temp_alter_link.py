import sqlite3

def alter():
    conn = sqlite3.connect("api_keys.db")
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN linked_api_key VARCHAR;")
        print("Added linked_api_key to users table successfully!")
    except Exception as e:
        print(f"Error (already exists?): {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    alter()
