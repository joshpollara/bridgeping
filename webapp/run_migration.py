#!/usr/bin/env python3
import sqlite3
from datetime import datetime
import os

# Use the correct database path
DB_FILE = os.environ.get('DATABASE_PATH', '/app/data/bridgeping.db')
if not os.path.exists(DB_FILE):
    DB_FILE = '/home/josh/bridgeping/data/bridgeping.db'

def create_bridge_opening_links():
    """Create a link table between bridges and their opening schedules."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print(f"Using database: {DB_FILE}")
    print("Creating bridge_opening_links table if not exists...")
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
    
    print(f"Found {len(opening_locations)} unique opening locations")
    
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
                    if matched_locations % 10 == 0:
                        print(f"Progress: {matched_locations} locations linked...")
            except Exception as e:
                print(f"Error linking bridge: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\nLinked {matched_locations} out of {len(opening_locations)} opening locations to bridges.")
    return matched_locations

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
    
    # Bridges with openings
    cursor.execute("SELECT COUNT(DISTINCT bridge_id) FROM bridge_opening_links")
    bridges_with_openings = cursor.fetchone()[0]
    print(f"Bridges with opening data: {bridges_with_openings}")
    
    conn.close()

if __name__ == "__main__":
    print("=== Running Bridge Opening Links Migration ===")
    
    # Create bridge-opening links
    matched = create_bridge_opening_links()
    
    # Show statistics
    if matched > 0:
        show_statistics()
    else:
        print("\nNo bridges were linked. This might indicate:")
        print("- The bridges and openings are too far apart (>100m)")
        print("- The coordinate precision doesn't match")
        print("- Need to run bridge sync scripts first")