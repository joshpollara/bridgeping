#!/usr/bin/env python3
import sqlite3
from datetime import datetime

DB_FILE = "/home/josh/claude/bridgeping/app/bridgeping.db"

def add_bridge_id_column():
    """Add bridge_id column to watched_bridges table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(watched_bridges)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'bridge_id' not in columns:
        print("Adding bridge_id column to watched_bridges table...")
        cursor.execute("""
            ALTER TABLE watched_bridges 
            ADD COLUMN bridge_id INTEGER REFERENCES bridges(id)
        """)
        conn.commit()
        print("Column added successfully.")
    else:
        print("bridge_id column already exists.")
    
    conn.close()

def add_bridge_location_to_openings():
    """Add latitude/longitude index to bridge_openings for faster matching."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("Creating spatial index on bridge_openings...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bridge_openings_location 
        ON bridge_openings(latitude, longitude)
    """)
    
    conn.commit()
    conn.close()

def match_existing_bridges():
    """Match existing watched bridges to the bridges table based on name."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all watched bridges without bridge_id
    cursor.execute("""
        SELECT id, bridge_name 
        FROM watched_bridges 
        WHERE bridge_id IS NULL
    """)
    
    unmatched = cursor.fetchall()
    matched_count = 0
    
    for watch_id, bridge_name in unmatched:
        # Try to find a matching bridge
        # First try exact name match
        cursor.execute("""
            SELECT id FROM bridges 
            WHERE name = ? 
            LIMIT 1
        """, (bridge_name,))
        
        result = cursor.fetchone()
        
        if not result and ', ' in bridge_name:
            # Try matching just the bridge name part (before city)
            name_part = bridge_name.split(',')[0].strip()
            cursor.execute("""
                SELECT id FROM bridges 
                WHERE name = ? 
                LIMIT 1
            """, (name_part,))
            result = cursor.fetchone()
        
        if result:
            # Update the watched bridge with the bridge_id
            cursor.execute("""
                UPDATE watched_bridges 
                SET bridge_id = ? 
                WHERE id = ?
            """, (result[0], watch_id))
            matched_count += 1
            print(f"Matched '{bridge_name}' to bridge ID {result[0]}")
    
    conn.commit()
    conn.close()
    
    print(f"\nMatched {matched_count} out of {len(unmatched)} watched bridges.")

def create_bridge_opening_links():
    """Create a link table between bridges and their opening schedules."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("Creating bridge_opening_links table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridge_opening_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bridge_id INTEGER NOT NULL REFERENCES bridges(id),
            opening_location_key TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bridge_id, opening_location_key)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bridge_opening_links_location 
        ON bridge_opening_links(latitude, longitude)
    """)
    
    # Match bridges to opening locations based on coordinates
    print("Matching bridges to opening locations...")
    
    # Get unique opening locations
    cursor.execute("""
        SELECT DISTINCT 
            ROUND(latitude, 4) as lat,
            ROUND(longitude, 4) as lon
        FROM bridge_openings
    """)
    
    opening_locations = cursor.fetchall()
    matched_locations = 0
    
    for lat, lon in opening_locations:
        # Find bridges within ~100 meters of this location
        cursor.execute("""
            SELECT id, name, latitude, longitude
            FROM bridges
            WHERE ABS(latitude - ?) < 0.001 
            AND ABS(longitude - ?) < 0.001
            ORDER BY 
                (latitude - ?) * (latitude - ?) + 
                (longitude - ?) * (longitude - ?)
            LIMIT 1
        """, (lat, lon, lat, lat, lon, lon))
        
        bridge = cursor.fetchone()
        
        if bridge:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO bridge_opening_links 
                    (bridge_id, opening_location_key, latitude, longitude)
                    VALUES (?, ?, ?, ?)
                """, (bridge[0], f"{lat},{lon}", lat, lon))
                
                if cursor.rowcount > 0:
                    matched_locations += 1
                    print(f"Linked bridge '{bridge[1]}' to opening location {lat},{lon}")
            except Exception as e:
                print(f"Error linking bridge: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\nLinked {matched_locations} out of {len(opening_locations)} opening locations to bridges.")

def show_statistics():
    """Show statistics about the linked data."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("\n=== Database Statistics ===")
    
    # Total bridges
    cursor.execute("SELECT COUNT(*) FROM bridges")
    total_bridges = cursor.fetchone()[0]
    print(f"Total bridges (OSM): {total_bridges}")
    
    # Total opening locations
    cursor.execute("SELECT COUNT(DISTINCT ROUND(latitude, 4) || ',' || ROUND(longitude, 4)) FROM bridge_openings")
    total_opening_locations = cursor.fetchone()[0]
    print(f"Total opening locations (NDW): {total_opening_locations}")
    
    # Linked bridges
    cursor.execute("SELECT COUNT(*) FROM bridge_opening_links")
    linked_count = cursor.fetchone()[0]
    print(f"Linked opening locations: {linked_count}")
    
    # Watched bridges with bridge_id
    cursor.execute("SELECT COUNT(*) FROM watched_bridges WHERE bridge_id IS NOT NULL")
    watched_with_id = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM watched_bridges")
    total_watched = cursor.fetchone()[0]
    print(f"Watched bridges with bridge_id: {watched_with_id}/{total_watched}")
    
    conn.close()

def main():
    print("=== Bridge Data Migration ===")
    print(f"Database: {DB_FILE}")
    print()
    
    # Step 1: Add bridge_id column
    add_bridge_id_column()
    
    # Step 2: Add indexes
    add_bridge_location_to_openings()
    
    # Step 3: Match existing watched bridges
    match_existing_bridges()
    
    # Step 4: Create bridge-opening links
    create_bridge_opening_links()
    
    # Step 5: Show statistics
    show_statistics()

if __name__ == "__main__":
    main()