import sqlite3
import os
import datetime

db_path = './api_keys.db'
if not os.path.exists(db_path):
    print("Database not found. Exiting.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

current_month = datetime.datetime.utcnow().strftime('%Y-%m')

try:
    cursor.execute("ALTER TABLE users ADD COLUMN total_verifications INTEGER DEFAULT 0")
    print("Added total_verifications")
except Exception as e:
    print(f"Skipped total_verifications: {e}")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN monthly_verifications INTEGER DEFAULT 0")
    print("Added monthly_verifications")
except Exception as e:
    print(f"Skipped monthly_verifications: {e}")

try:
    cursor.execute(f"ALTER TABLE users ADD COLUMN current_month VARCHAR DEFAULT '{current_month}'")
    print("Added current_month")
except Exception as e:
    print(f"Skipped current_month: {e}")

conn.commit()
conn.close()
print("Migration completed.")
