#!/usr/bin/env python3
"""Test what the timeline query should return for user's watched bridges"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('../bridgeping.db')
cursor = conn.cursor()

# Check all openings in the time range you mentioned
cursor.execute("""
    SELECT 
        bo.latitude, 
        bo.longitude,
        ROUND(bo.latitude, 4) || ',' || ROUND(bo.longitude, 4) as loc_key,
        datetime(bo.start_time, 'localtime') as start_time,
        b.name as bridge_name,
        b.city,
        wb.user_id
    FROM bridge_openings bo
    LEFT JOIN bridge_opening_links bol 
        ON ROUND(bo.latitude, 4) = ROUND(bol.latitude, 4) 
        AND ROUND(bo.longitude, 4) = ROUND(bol.longitude, 4)
    LEFT JOIN bridges b ON b.id = bol.bridge_id
    LEFT JOIN watched_bridges wb ON wb.bridge_id = b.id AND wb.user_id = 1
    WHERE datetime(bo.start_time, 'localtime') BETWEEN '2025-08-04 16:00' AND '2025-08-04 20:00'
    AND bo.latitude > 52 AND bo.latitude < 53
    AND bo.longitude > 4 AND bo.longitude < 5
    ORDER BY bo.start_time
    LIMIT 20
""")

print("Bridge openings and whether they're watched by user 1:")
print("-" * 80)
for row in cursor.fetchall():
    lat, lon, loc_key, start_time, bridge_name, city, user_id = row
    watched = "WATCHED" if user_id == 1 else "not watched"
    name = bridge_name or f"Unnamed bridge at {loc_key}"
    city_str = city or "Unknown"
    print(f"{start_time} | {name:40} | {city_str:15} | {watched}")

conn.close()