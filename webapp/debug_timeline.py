#!/usr/bin/env python3
import sqlite3
from datetime import datetime

# Connect to database
conn = sqlite3.connect('../bridgeping.db')
cursor = conn.cursor()

# Simulate what the timeline view does for user 1
user_id = 1

# Get watched bridges with bridge_ids
cursor.execute("""
    SELECT bridge_id, bridge_name FROM watched_bridges 
    WHERE user_id = ? AND bridge_id IS NOT NULL
""", (user_id,))
watched = cursor.fetchall()
print(f"Watched bridges: {watched}")

bridge_ids = [b[0] for b in watched]
print(f"Bridge IDs: {bridge_ids}")

# Get location keys for these bridges
placeholders = ','.join(['?' for _ in bridge_ids])
cursor.execute(f"""
    SELECT bol.opening_location_key, b.id, b.name, b.display_name, 
           b.street_name, b.water_name, b.city
    FROM bridge_opening_links bol
    JOIN bridges b ON b.id = bol.bridge_id
    WHERE bol.bridge_id IN ({placeholders})
""", bridge_ids)

bridge_location_map = {}
for row in cursor.fetchall():
    lat, lon = row[0].split(',')
    location_key = f"{float(lat):.4f},{float(lon):.4f}"
    name = row[2] or row[3] or (f"{row[4]} Bridge" if row[4] else f"Bridge in {row[6]}")
    bridge_location_map[location_key] = {
        'id': row[1],
        'name': name,
        'city': row[6]
    }
    print(f"Added to map: {location_key} -> {name}")

print(f"\nbridge_location_map: {bridge_location_map}")

# Get opening events
location_keys = list(bridge_location_map.keys())
if location_keys:
    placeholders = ','.join(['?' for _ in location_keys])
    cursor.execute(f"""
        SELECT 
            ROUND(latitude, 4) || ',' || ROUND(longitude, 4) as location_key,
            datetime(start_time, 'localtime') as start_time,
            datetime(end_time, 'localtime') as end_time
        FROM bridge_openings
        WHERE ROUND(latitude, 4) || ',' || ROUND(longitude, 4) IN ({placeholders})
        AND datetime(start_time) > datetime('now')
        ORDER BY start_time
        LIMIT 10
    """, location_keys)
    
    print("\nOpenings found:")
    for row in cursor.fetchall():
        bridge_info = bridge_location_map.get(row[0])
        if bridge_info:
            print(f"  {row[1]} - {row[2]}: {bridge_info['name']} at {row[0]}")
        else:
            print(f"  {row[1]} - {row[2]}: NO MATCH for {row[0]}")

conn.close()