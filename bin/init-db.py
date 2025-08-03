#!/usr/bin/env python3
"""
Startup script to initialize the database on first run.
"""
import os
import sys
from pathlib import Path

# Add app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.database import init_db, DATABASE_PATH

def main():
    """Initialize database tables if needed."""
    print("🌉 Initializing Bridge Ping database...")
    
    # Create data directory if it doesn't exist
    data_dir = Path(DATABASE_PATH).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize database tables
    init_db()
    print("✅ Database initialized successfully!")
    
if __name__ == "__main__":
    main()
