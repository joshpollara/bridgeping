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

# URL-based watchlist models
class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    bridges = relationship("WatchlistBridge", back_populates="watchlist", cascade="all, delete-orphan")

class WatchlistBridge(Base):
    __tablename__ = "watchlist_bridges"

    id = Column(Integer, primary_key=True, index=True)
    watchlist_id = Column(Integer, ForeignKey("watchlists.id"), nullable=False)
    bridge_name = Column(String, nullable=False)
    bridge_id = Column(String, nullable=True)  # Reference to bridges table
    created_at = Column(DateTime, default=datetime.utcnow)
    
    watchlist = relationship("Watchlist", back_populates="bridges")

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
            osm_id TEXT UNIQUE,
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
    
    # Run migrations for existing tables
    run_migrations(cursor)
    
    conn.commit()
    conn.close()

def run_migrations(cursor):
    """Run database migrations to update existing schemas."""
    # Migration 1: Add tags column to bridges table if it doesn't exist
    cursor.execute("PRAGMA table_info(bridges)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'tags' not in columns:
        print("Migration: Adding 'tags' column to bridges table...")
        cursor.execute("ALTER TABLE bridges ADD COLUMN tags TEXT")
        print("✅ Tags column added successfully!")
    
    # Migration 2: Add UNIQUE constraint to osm_id if it doesn't exist
    # Check if osm_id has a unique constraint
    cursor.execute("PRAGMA index_list(bridges)")
    indexes = cursor.fetchall()
    has_osm_id_unique = False
    
    for idx in indexes:
        if idx[1].startswith('sqlite_autoindex'):
            cursor.execute(f"PRAGMA index_info('{idx[1]}')")
            info = cursor.fetchall()
            for col in info:
                cursor.execute("PRAGMA table_info(bridges)")
                table_info = cursor.fetchall()
                if col[1] < len(table_info) and table_info[col[1]][1] == 'osm_id':
                    has_osm_id_unique = True
                    break
    
    if not has_osm_id_unique:
        print("Migration: Creating unique index on osm_id...")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bridges_osm_id ON bridges(osm_id)")
        print("✅ Unique constraint added to osm_id!")
    
    # Add future migrations here as needed
    # Example:
    # if 'some_column' not in columns:
    #     cursor.execute("ALTER TABLE some_table ADD COLUMN some_column TEXT")
