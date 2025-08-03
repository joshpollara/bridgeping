from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import sqlite3

# Use environment variable or default path
DATABASE_PATH = os.environ.get('DATABASE_PATH', '../bridgeping.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    calendar_token = Column(String, unique=True, index=True)
    
    watched_bridges = relationship("WatchedBridge", back_populates="user", cascade="all, delete-orphan")

class WatchedBridge(Base):
    __tablename__ = "watched_bridges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bridge_name = Column(String, nullable=False)
    bridge_id = Column(Integer, nullable=True)  # Reference to bridges table
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="watched_bridges")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # Create SQLAlchemy tables
    Base.metadata.create_all(bind=engine)
    
    # Create other tables that aren't managed by SQLAlchemy
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create bridges table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            city TEXT,
            osm_id INTEGER,
            bridge_type TEXT,
            street_name TEXT,
            water_name TEXT,
            neighborhood TEXT,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create bridge_openings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bridge_openings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT UNIQUE,
            bridge_name TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            creation_time TEXT,
            version_time TEXT,
            source TEXT DEFAULT 'NDW',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create bridge_opening_links table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bridge_opening_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bridge_id INTEGER NOT NULL,
            opening_location_key TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bridge_id) REFERENCES bridges(id),
            UNIQUE(bridge_id, opening_location_key)
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridges_coords ON bridges(latitude, longitude)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridge_openings_coords ON bridge_openings(latitude, longitude)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridge_openings_time ON bridge_openings(start_time, end_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridges_city ON bridges(city)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bridges_name ON bridges(name)')
    
    conn.commit()
    conn.close()
