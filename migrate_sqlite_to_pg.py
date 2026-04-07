import os
import sys
import logging
from sqlalchemy import create_engine, text, insert
from sqlalchemy.orm import sessionmaker

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import existing application models
from database import Base, User, Subscription, UserFile, EmailResult

# Configurable endpoints
SQLITE_URL = os.getenv("SQLITE_URL", "sqlite:///./api_keys.db")
POSTGRES_URL = os.getenv("POSTGRES_URL")

if not POSTGRES_URL:
    logger.error("FATAL ERROR: POSTGRES_URL environment variable is not set. Execution aborted.")
    sys.exit(1)

# Initialize engines
sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(POSTGRES_URL)

SqliteSession = sessionmaker(bind=sqlite_engine)
PgSession = sessionmaker(bind=pg_engine)

def reset_pg_sequences(pg_session):
    """After inserting fixed IDs, we must increment the postgres ID sequences to avoid overlaps."""
    tables_and_seqs = {
        'users': 'users_id_seq',
        'subscriptions': 'subscriptions_id_seq',
        'user_files': 'user_files_id_seq',
        'email_results': 'email_results_id_seq'
    }
    
    for table, seq in tables_and_seqs.items():
        try:
            # Safely set the sequence to the maximum ID found + 1, so new inserts succeed
            pg_session.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false);"))
            logger.info(f"Successfully reset sequence {seq} for table '{table}'")
        except Exception as e:
            logger.warning(f"Could not reset sequence {seq}: {e}")

def main():
    logger.info("Initializing Postgres schema...")
    Base.metadata.create_all(bind=pg_engine)
    
    sqlite_session = SqliteSession()
    pg_session = PgSession()
    
    # 1. Verification of Empty State
    logger.info("Checking for pre-existing Postgres data (must be empty to proceed safely)...")
    for model in [User, Subscription, UserFile, EmailResult]:
        if pg_session.query(model).first():
            logger.error(f"Table '{model.__tablename__}' is NOT empty in PostgreSQL! Aborting migration to prevent data overwrite.")
            sys.exit(1)
            
    # 2. Ordered Migration Array
    models_to_migrate = [
        ("users", User),
        ("subscriptions", Subscription),
        ("user_files", UserFile),
        ("email_results", EmailResult)
    ]
    
    counts = {}
    
    try:
        # Wrap everything in a single transaction (Atomic execution)
        pg_session.begin()
        
        for table_name, model in models_to_migrate:
            logger.info(f"--- Starting migration for {table_name} ---")
            
            total_records = sqlite_session.query(model).count()
            counts[table_name] = {'sqlite': total_records, 'pg': 0}
            
            if total_records == 0:
                logger.info(f"No records found in {table_name}. Skipping.")
                continue
                
            batch_size = 5000
            offset = 0
            
            while offset < total_records:
                # Fetch dynamically using offset and limit to save system RAM
                records = sqlite_session.query(model).order_by(model.id).offset(offset).limit(batch_size).all()
                if not records:
                    break
                    
                # Export row mappings quickly for bulk insert
                data_dicts = [{col.name: getattr(r, col.name) for col in model.__table__.columns} for r in records]
                
                # Bulk save using low-level core insert
                pg_session.execute(insert(model), data_dicts)
                
                counts[table_name]['pg'] += len(data_dicts)
                offset += batch_size
                logger.info(f"  Inserted {counts[table_name]['pg']}/{total_records} into {table_name}")
                
        # 3. Reset Sequences after bulk inserting assigned IDs
        logger.info("Resetting sequence counters for Postgres...")
        reset_pg_sequences(pg_session)
        
        # 4. Final Validation Phase (Integrity checks before committing)
        logger.info("Validating dataset integrity...")
        for table_name, _ in models_to_migrate:
            sqlite_c = counts[table_name]['sqlite']
            pg_c = counts[table_name]['pg']
            logger.info(f"Validation: {table_name} SQLite={sqlite_c} vs Postgres={pg_c}")
            if sqlite_c != pg_c:
                raise AssertionError(f"Integrity check failed for {table_name}! Expected {sqlite_c}, got {pg_c}")
        
        # 5. Lock and load data
        pg_session.commit()
        logger.info("✅ Migration executed seamlessly and COMMITTED to PostgreSQL.")
        
    except Exception as e:
        # Emergency brake - revert all partial writes
        pg_session.rollback()
        logger.error(f"❌ Migration failed! Rolled back current transaction completely.")
        logger.error(f"Error context: {str(e)}")
        sys.exit(1)
        
    finally:
        # Dispose memory
        sqlite_session.close()
        pg_session.close()

if __name__ == "__main__":
    main()
