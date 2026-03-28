import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

# DO App Platform provides DATABASE_URL env var
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend_data.db")

# DigitalOcean provides 'postgres://', but SQLAlchemy requires 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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

# Create tables
Base.metadata.create_all(bind=engine)

# Migration Helper: Add session_string if missing
def run_migrations():
    try:
        with SessionLocal() as session:
            # Check telegram_config
            try:
                session.execute(text("ALTER TABLE telegram_config ADD COLUMN session_string TEXT"))
                session.commit()
            except: session.rollback()
            
            # Check sender_config
            try:
                session.execute(text("ALTER TABLE sender_config ADD COLUMN session_string TEXT"))
                session.commit()
            except: session.rollback()
            
            # Check target_groups
            try:
                session.execute(text("ALTER TABLE target_groups ADD COLUMN is_sender_joined BOOLEAN DEFAULT 0"))
                session.commit()
            except: session.rollback()
    except Exception as e:
        print(f"Migration hint: {e}")

run_migrations()
