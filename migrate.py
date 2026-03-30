import sqlite3
import os

def migrate():
    print("Starting migration...")
    try:
        conn = sqlite3.connect('api_keys.db', timeout=10)
        cursor = conn.cursor()
        
        # Try adding columns to users table
        columns_users = [
            ('partner_status', 'VARCHAR'),
            ('partner_daily_limit', 'INTEGER'),
            ('partner_credits_used_today', 'INTEGER DEFAULT 0'),
            ('partner_limit_reset_date', 'DATETIME')
        ]
        for col_name, col_type in columns_users:
            try:
                cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
                print(f'Added {col_name} to users')
            except sqlite3.OperationalError as e:
                if 'duplicate column name' in str(e).lower():
                    print(f'{col_name} already exists in users')
                else:
                    print(f'Error adding {col_name}: {e}')
                    
        # Try adding columns to user_files table
        try:
            cursor.execute('ALTER TABLE user_files ADD COLUMN pool_api_key VARCHAR')
            print('Added pool_api_key to user_files')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                print('pool_api_key already exists in user_files')
            else:
                print(f'Error adding pool_api_key: {e}')
                
        conn.commit()
        conn.close()
        print('Database migration complete.')
    except Exception as e:
        print('Error during migration:', e)

if __name__ == "__main__":
    migrate()
