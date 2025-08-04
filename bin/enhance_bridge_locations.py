#!/usr/bin/env python3
import sqlite3
import requests
import json
import time
from collections import defaultdict
import os

DB_FILE = os.environ.get('DATABASE_PATH', '/app/data/bridgeping.db')

def add_location_columns():
    """Add columns for enhanced location data."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if columns exist
    cursor.execute("PRAGMA table_info(bridges)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    columns_to_add = [
        ("street_name", "TEXT"),
        ("neighborhood", "TEXT"),
        ("water_name", "TEXT"),
        ("display_name", "TEXT")
    ]
    
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            print(f"Adding {col_name} column...")
            cursor.execute(f"ALTER TABLE bridges ADD COLUMN {col_name} {col_type}")
    
    conn.commit()
    conn.close()

def fetch_nearby_features(lat, lon, radius=50):
    """Fetch nearby features from Overpass API."""
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    # Query for nearby streets and waterways
    query = f"""
    [out:json][timeout:10];
    (
        way["highway"](around:{radius},{lat},{lon});
        way["waterway"](around:{radius},{lat},{lon});
        way["name"](around:{radius},{lat},{lon});
    );
    out tags;
    """
    
    try:
        response = requests.post(overpass_url, data={'data': query}, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        streets = []
        waterways = []
        
        for element in data.get('elements', []):
            tags = element.get('tags', {})
            name = tags.get('name')
            
            if not name:
                continue
                
            if 'highway' in tags:
                streets.append(name)
            elif 'waterway' in tags:
                waterways.append(name)
        
        return {
            'streets': list(set(streets))[:2],  # Top 2 unique street names
            'waterways': list(set(waterways))[:1]  # Top waterway
        }
    except Exception as e:
        print(f"Error fetching features for {lat},{lon}: {e}")
        return {'streets': [], 'waterways': []}

def reverse_geocode_nominatim(lat, lon):
    """Use Nominatim for reverse geocoding."""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        'lat': lat,
        'lon': lon,
        'format': 'json',
        'addressdetails': 1,
        'zoom': 18  # Street level detail
    }
    headers = {
        'User-Agent': 'BridgePing/1.0'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        address = data.get('address', {})
        
        return {
            'street': address.get('road') or address.get('pedestrian'),
            'neighborhood': address.get('neighbourhood') or address.get('suburb') or address.get('district'),
            'water': address.get('water') or address.get('waterway'),
            'display_name': data.get('display_name', '')
        }
    except Exception as e:
        print(f"Nominatim error for {lat},{lon}: {e}")
        return {}

def enhance_bridge_locations(limit=None):
    """Enhance bridge data with better location information."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get bridges without enhanced location data
    query = """
        SELECT id, name, latitude, longitude, city, tags
        FROM bridges
        WHERE display_name IS NULL OR display_name = ''
        ORDER BY 
            CASE WHEN name = '' THEN 0 ELSE 1 END,  -- Unnamed bridges first
            id
    """
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query)
    bridges = cursor.fetchall()
    
    print(f"Enhancing location data for {len(bridges)} bridges...")
    if len(bridges) == 0:
        print("All bridges already have location data!")
        return
    
    start_time = time.time()
    errors = 0
    
    for i, (bridge_id, name, lat, lon, city, tags_json) in enumerate(bridges):
        if i % 100 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(bridges) - i) / rate if rate > 0 else 0
            print(f"\nProgress: {i}/{len(bridges)} ({i*100/len(bridges):.1f}%) - "
                  f"Rate: {rate:.1f} bridges/sec - ETA: {eta/60:.1f} minutes")
        
        # Parse existing tags
        existing_tags = {}
        if tags_json:
            try:
                existing_tags = json.loads(tags_json)
            except:
                pass
        
        # Try Nominatim reverse geocoding
        geocode_data = reverse_geocode_nominatim(lat, lon)
        
        # Also fetch nearby features from OSM
        nearby = fetch_nearby_features(lat, lon)
        
        # Combine data
        street_name = (
            geocode_data.get('street') or 
            existing_tags.get('addr:street') or
            (nearby['streets'][0] if nearby['streets'] else None)
        )
        
        water_name = (
            geocode_data.get('water') or
            (nearby['waterways'][0] if nearby['waterways'] else None)
        )
        
        neighborhood = geocode_data.get('neighborhood')
        
        # Create display name
        if not name and street_name:
            if water_name:
                display_name = f"{street_name} over {water_name}"
            else:
                display_name = f"{street_name} Bridge"
        else:
            display_name = geocode_data.get('display_name', '')
        
        # Update database
        cursor.execute("""
            UPDATE bridges
            SET street_name = ?,
                neighborhood = ?,
                water_name = ?,
                display_name = ?
            WHERE id = ?
        """, (street_name, neighborhood, water_name, display_name, bridge_id))
        
        if i % 100 != 0:  # Only print details for non-progress updates
            print(f"  Street: {street_name}")
            print(f"  Water: {water_name}")
            print(f"  Neighborhood: {neighborhood}")
        
        # Be nice to the APIs
        time.sleep(1)
        
        # Commit every 100 records
        if (i + 1) % 100 == 0:
            conn.commit()
    
    conn.commit()
    conn.close()
    
    total_time = time.time() - start_time
    print(f"\n=== Enhancement Complete ===")
    print(f"Processed: {len(bridges)} bridges")
    print(f"Errors: {errors}")
    print(f"Time: {total_time/60:.1f} minutes")
    print(f"Average: {total_time/len(bridges):.2f} seconds per bridge")

def show_sample_results():
    """Show some sample enhanced bridges."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("\n=== Sample Enhanced Bridges ===")
    
    cursor.execute("""
        SELECT name, street_name, water_name, neighborhood, city, display_name
        FROM bridges
        WHERE street_name IS NOT NULL
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        print(f"\nOriginal name: {row[0] or 'unnamed'}")
        print(f"Street: {row[1]}")
        print(f"Water: {row[2]}")
        print(f"Neighborhood: {row[3]}")
        print(f"City: {row[4]}")
        print(f"Display: {row[5]}")
    
    conn.close()

def main():
    print("=== Bridge Location Enhancement ===")
    
    # Add columns
    add_location_columns()
    
    # Enhance ALL bridges without location data
    print("\nEnhancing all bridges without location data...")
    print("This will take a while on first run, but subsequent runs will be fast!")
    enhance_bridge_locations()  # No limit - process all
    
    # Show results
    show_sample_results()

if __name__ == "__main__":
    main()