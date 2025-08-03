#!/usr/bin/env python3
import sqlite3
import secrets

DB_FILE = "../bridgeping.db"

def add_calendar_token_column():
    """Add calendar_token column to users table and generate tokens."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'calendar_token' not in columns:
        print("Adding calendar_token column...")
        cursor.execute("ALTER TABLE users ADD COLUMN calendar_token TEXT")
        
        # Generate unique tokens for existing users
        cursor.execute("SELECT id FROM users")
        users = cursor.fetchall()
        
        for user_id, in users:
            token = secrets.token_urlsafe(32)
            cursor.execute("UPDATE users SET calendar_token = ? WHERE id = ?", (token, user_id))
            print(f"Generated token for user {user_id}")
        
        # Create unique index
        cursor.execute("CREATE UNIQUE INDEX idx_calendar_token ON users(calendar_token)")
        
        conn.commit()
        print("Calendar tokens added successfully!")
    else:
        print("Calendar token column already exists")
    
    conn.close()

if __name__ == "__main__":
    add_calendar_token_column()