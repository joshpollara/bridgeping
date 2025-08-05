#!/usr/bin/env python3
"""
Migration script to convert from user-based watchlists to URL-based watchlists
"""
import sqlite3
import os
import sys
from datetime import datetime
from name_generator import generate_unique_watchlist_name

def migrate_database(db_path):
    """Migrate from user-based to URL-based watchlists"""
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if migration is needed
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='watchlists'")
        if cursor.fetchone():
            print("Migration already completed - watchlists table exists")
            return True
        
        print("Starting migration to URL-based watchlists...")
        
        # Create new tables
        print("Creating new watchlist tables...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_bridges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id INTEGER NOT NULL,
                bridge_name TEXT NOT NULL,
                bridge_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX idx_watchlist_name ON watchlists(name)")
        cursor.execute("CREATE INDEX idx_watchlist_bridges_watchlist_id ON watchlist_bridges(watchlist_id)")
        cursor.execute("CREATE INDEX idx_watchlist_bridges_bridge_id ON watchlist_bridges(bridge_id)")
        
        # Check if we have existing user data to migrate
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone():
            print("Migrating existing user watchlists...")
            
            # Function to check if name exists
            def name_exists(name):
                cursor.execute("SELECT 1 FROM watchlists WHERE name = ?", (name,))
                return cursor.fetchone() is not None
            
            # Get all users with their watchlists
            cursor.execute("""
                SELECT u.id, u.email, u.calendar_token, wb.bridge_name, wb.bridge_id, wb.created_at
                FROM users u
                LEFT JOIN watched_bridges wb ON u.id = wb.user_id
                ORDER BY u.id
            """)
            
            user_data = cursor.fetchall()
            current_user_id = None
            watchlist_name = None
            watchlist_id = None
            migrated_count = 0
            
            for row in user_data:
                user_id, email, calendar_token, bridge_name, bridge_id, created_at = row
                
                # Create new watchlist for each user
                if user_id != current_user_id:
                    current_user_id = user_id
                    watchlist_name = generate_unique_watchlist_name(name_exists)
                    
                    cursor.execute(
                        "INSERT INTO watchlists (name, created_at) VALUES (?, ?)",
                        (watchlist_name, datetime.now())
                    )
                    watchlist_id = cursor.lastrowid
                    migrated_count += 1
                    print(f"  Created watchlist '{watchlist_name}' for user {email}")
                
                # Add bridges to the watchlist
                if bridge_name and watchlist_id:
                    cursor.execute(
                        "INSERT INTO watchlist_bridges (watchlist_id, bridge_name, bridge_id, created_at) VALUES (?, ?, ?, ?)",
                        (watchlist_id, bridge_name, bridge_id, created_at or datetime.now())
                    )
            
            print(f"Migrated {migrated_count} user watchlists")
            
            # Create a migration log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migration_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT,
                    old_calendar_token TEXT,
                    new_watchlist_name TEXT,
                    migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Log the migration for reference
            cursor.execute("""
                INSERT INTO migration_log (user_email, old_calendar_token, new_watchlist_name)
                SELECT u.email, u.calendar_token, w.name
                FROM users u
                JOIN (
                    SELECT MIN(w.id) as watchlist_id, w.name
                    FROM watchlists w
                    GROUP BY w.name
                ) w
            """)
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Show summary
        cursor.execute("SELECT COUNT(*) FROM watchlists")
        watchlist_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM watchlist_bridges")
        bridge_count = cursor.fetchone()[0]
        
        print(f"\nSummary:")
        print(f"  - Created {watchlist_count} watchlists")
        print(f"  - Migrated {bridge_count} bridge associations")
        print(f"\nNote: Old user tables have been preserved for rollback if needed")
        
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    # Get database path from environment or use default
    db_path = os.environ.get('DATABASE_PATH', '/app/data/bridgeping.db')
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    print(f"Using database: {db_path}")
    
    if migrate_database(db_path):
        print("\nMigration successful!")
        print("Next steps:")
        print("1. Update the application code to use the new watchlist system")
        print("2. Test the new URL-based watchlists")
        print("3. Once confirmed working, you can drop the old user tables")
    else:
        print("\nMigration failed!")
        sys.exit(1)