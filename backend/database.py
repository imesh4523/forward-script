import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

# DO App Platform provides DATABASE_URL env var
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend_data.db")

# DigitalOcean provides 'postgres://', but SQLAlchemy requires 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure SSL mode for PostgreSQL (required for DO Managed DB)
if "postgresql" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

is_sqlite = DATABASE_URL.startswith("sqlite")

connect_args = {}
if is_sqlite:
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

# Enable WAL mode for better concurrent access (SQLite only)
if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TelegramConfig(Base):
    """Main/Source account - channel එකේ posts බලන ගිණුම"""
    __tablename__ = "telegram_config"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(String)
    api_hash = Column(String)
    phone_number = Column(String)
    is_authenticated = Column(Boolean, default=False)
    session_string = Column(String, nullable=True) # For StringSession support (DO App Platform)

class SenderConfig(Base):
    """Sender account - groups වලට messages යවන ගිණුම"""
    __tablename__ = "sender_config"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(String)
    api_hash = Column(String)
    phone_number = Column(String)
    is_authenticated = Column(Boolean, default=False)
    session_string = Column(String, nullable=True) # For StringSession support (DO App Platform)

class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True, index=True)
    group_id_or_username = Column(String, unique=True, index=True)
    group_title = Column(String)
    is_joined = Column(Boolean, default=False)
    is_selected = Column(Boolean, default=True)
    is_sender_joined = Column(Boolean, default=False)

class TargetGroup(Base):
    __tablename__ = "target_groups"
    id = Column(Integer, primary_key=True, index=True)
    group_id_or_username = Column(String, index=True)
    group_title = Column(String, default="")
    is_joined = Column(Boolean, default=False)
    is_selected = Column(Boolean, default=True)
    is_sender_joined = Column(Boolean, default=False)

class ForwardingConfig(Base):
    __tablename__ = "forwarding_config"
    id = Column(Integer, primary_key=True, index=True)
    post_link = Column(String, default="")
    delay_min = Column(Integer, default=30)
    delay_max = Column(Integer, default=120)
    hourly_count = Column(Integer, default=3)
    join_delay_minutes = Column(Integer, default=60)
    total_sent_count = Column(Integer, default=0)
    is_bot_running = Column(Boolean, default=False)
    cycle_rest_minutes = Column(Integer, default=3)

# Grant permissions on public schema (required for DigitalOcean Managed PostgreSQL)
def grant_schema_permissions():
    if not is_sqlite:
        try:
            with engine.connect() as conn:
                conn.execute(text("GRANT ALL ON SCHEMA public TO PUBLIC"))
                conn.commit()
                print("INFO: Granted schema permissions.")
        except Exception as e:
            print(f"INFO: Schema grant skipped (may already exist): {e}")

grant_schema_permissions()

# Create tables
try:
    Base.metadata.create_all(bind=engine)
    print("INFO: Tables created/verified successfully.")
except Exception as e:
    print(f"ERROR: Could not create tables: {e}")

# Migration Helper: Add columns if missing safely
def run_migrations():
    print("INFO: Checking for database migrations...")
    from sqlalchemy import inspect
    try:
        inspector = inspect(engine)
        
        # Helper to add column if it doesn't exist
        def add_column_if_not_exists(table_name, column_name, col_type_and_default):
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            if column_name not in columns:
                with engine.begin() as conn:
                    print(f"INFO: Migrating: Adding {column_name} to {table_name}...")
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {col_type_and_default}"))

        # 1. Add cycle_rest_minutes
        add_column_if_not_exists("forwarding_config", "cycle_rest_minutes", "INTEGER DEFAULT 3")
        # 2. Add total_sent_count
        add_column_if_not_exists("forwarding_config", "total_sent_count", "INTEGER DEFAULT 0")
        # 3. Add is_bot_running
        add_column_if_not_exists("forwarding_config", "is_bot_running", "BOOLEAN DEFAULT FALSE")
        # 4. Add is_sender_joined
        add_column_if_not_exists("target_groups", "is_sender_joined", "BOOLEAN DEFAULT FALSE")
        # 5. Session strings for accounts
        for table in ["telegram_config", "sender_config"]:
            add_column_if_not_exists(table, "session_string", "TEXT")

        print("INFO: Database migration check finished.")
    except Exception as e:
        print(f"ERROR: Global migration failed: {e}")

run_migrations()
