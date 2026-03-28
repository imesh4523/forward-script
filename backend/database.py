from sqlalchemy import create_engine, Column, Integer, String, Boolean, event
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./backend_data.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)

# Enable WAL mode for better concurrent access
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

class SenderConfig(Base):
    """Sender account - groups වලට messages යවන ගිණුම"""
    __tablename__ = "sender_config"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(String)
    api_hash = Column(String)
    phone_number = Column(String)
    is_authenticated = Column(Boolean, default=False)

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

Base.metadata.create_all(bind=engine)

from sqlalchemy.sql import text
from sqlalchemy.exc import OperationalError

try:
    with SessionLocal() as session:
        session.execute(text("ALTER TABLE target_groups ADD COLUMN is_sender_joined BOOLEAN DEFAULT 0"))
        session.commit()
except OperationalError:
    pass # Column already exists
