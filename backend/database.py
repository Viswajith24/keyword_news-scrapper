# ## Changes
# - Added content_hash column migration to CrawledURL table inspection.
# - Ensured ignore_robots column migration on SearchQuery table inspection.

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Ensure the database directory exists (using local DB in workspace)
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "keyword_scraper.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
)

# Enable WAL (Write-Ahead Logging) mode and synchronous=NORMAL on SQLite connections
# for high concurrency performance and prevention of database locks.
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")  # 30 seconds timeout
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Check table structures and execute simple SQLite migrations if needed
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    
    if 'crawled_urls' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('crawled_urls')]
        if 'matched_keywords' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE crawled_urls ADD COLUMN matched_keywords TEXT NULL;"))
            print("Database migration: added matched_keywords column to crawled_urls.")
        if 'content_hash' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE crawled_urls ADD COLUMN content_hash VARCHAR(255) NULL;"))
            print("Database migration: added content_hash column to crawled_urls.")
        if 'description' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE crawled_urls ADD COLUMN description TEXT NULL;"))
            print("Database migration: added description column to crawled_urls.")
        if 'full_content' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE crawled_urls ADD COLUMN full_content TEXT NULL;"))
            print("Database migration: added full_content column to crawled_urls.")
        if 'author' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE crawled_urls ADD COLUMN author VARCHAR(255) NULL;"))
            print("Database migration: added author column to crawled_urls.")
        if 'image_url' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE crawled_urls ADD COLUMN image_url TEXT NULL;"))
            print("Database migration: added image_url column to crawled_urls.")
            
    if 'search_queries' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('search_queries')]
        if 'ignore_robots' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE search_queries ADD COLUMN ignore_robots BOOLEAN DEFAULT 0;"))
            print("Database migration: added ignore_robots column to search_queries.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
