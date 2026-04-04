"""
One-shot migration: ensures all tables exist with all required columns.
Safe to run multiple times — skips columns/tables that already exist.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "api_keys.db")


def table_exists(cursor, table: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def add_column_if_missing(cursor, table: str, column: str, definition: str):
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"  ✅ Added  {table}.{column}")
    else:
        print(f"  ⏩ Exists {table}.{column}")


def main():
    print(f"Connecting to {DB_PATH} …\n")
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ── 1. Create tables if they don't exist yet ──────────────────────────────

    if not table_exists(cur, "email_results"):
        print("[email_results] Creating table …")
        cur.execute("""
            CREATE TABLE email_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER REFERENCES users(id),
                file_id       INTEGER REFERENCES user_files(id),
                email         TEXT    NOT NULL,
                status        TEXT,
                score         INTEGER DEFAULT 0,
                syntax_valid  INTEGER DEFAULT 0,
                is_disposable INTEGER DEFAULT 0,
                mx_found      INTEGER DEFAULT 0,
                smtp_response INTEGER,
                verified_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS ix_email_results_user_id    ON email_results(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_email_results_email       ON email_results(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_email_results_status      ON email_results(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_email_results_file_id     ON email_results(file_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_email_results_verified_at ON email_results(verified_at)")
        print("  ✅ email_results created\n")
    else:
        print("[email_results] Table exists — checking columns …")
        add_column_if_missing(cur, "email_results", "file_id",       "INTEGER REFERENCES user_files(id)")
        add_column_if_missing(cur, "email_results", "score",         "INTEGER DEFAULT 0")
        add_column_if_missing(cur, "email_results", "syntax_valid",  "INTEGER DEFAULT 0")
        add_column_if_missing(cur, "email_results", "is_disposable", "INTEGER DEFAULT 0")
        add_column_if_missing(cur, "email_results", "mx_found",      "INTEGER DEFAULT 0")
        add_column_if_missing(cur, "email_results", "smtp_response", "INTEGER")
        print()

    # ── 2. Add bulk-job tracking columns to user_files ────────────────────────

    if not table_exists(cur, "user_files"):
        print("[user_files] Table missing — will be created by SQLAlchemy on next app start.\n")
    else:
        print("[user_files] Table exists — checking columns …")
        add_column_if_missing(cur, "user_files", "status",          "TEXT DEFAULT 'pending'")
        add_column_if_missing(cur, "user_files", "processed_count", "INTEGER DEFAULT 0")
        add_column_if_missing(cur, "user_files", "completed_at",    "DATETIME")
        print()

    con.commit()
    con.close()
    print("Migration complete ✅")


if __name__ == "__main__":
    main()
