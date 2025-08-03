#!/usr/bin/env python3
import requests
import json
import sqlite3
import time
from datetime import datetime

DB_FILE = "bridgeping.db"

def create_bridges_table():
    """Create table for static bridge data from OSM."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            osm_id TEXT UNIQUE NOT NULL,
            name TEXT,
            city TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            bridge_type TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bridges_coords 
        ON bridges(latitude, longitude)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bridges_name 
        ON bridges(name)
    """)
    
    conn.commit()
    conn.close()
    print("Bridges table created/verified.")

def fetch_bridges_from_osm(bbox=None):
    """Fetch bridge data from OpenStreetMap using Overpass API."""
    
    # Default to Netherlands bbox if not specified
    if bbox is None:
        # Netherlands bounding box: (min_lon, min_lat, max_lon, max_lat)
        bbox = (3.3, 50.7, 7.3, 53.6)
    
    # Overpass API query for bridges
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    # Query for ways and nodes tagged as bridges
    query = f"""
    [out:json][timeout:300];
    (
        way["bridge"]["bridge"!="no"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
        way["man_made"="bridge"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
        node["bridge"]["bridge"!="no"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
    );
    out center;
    """
    
    print(f"Fetching bridges from OSM for bbox: {bbox}")
    print("This may take a few minutes...")
    
    try:
        response = requests.post(overpass_url, data={'data': query}, timeout=300)
        response.raise_for_status()
        data = response.json()
        print(f"Received {len(data['elements'])} bridge elements from OSM")
        return data['elements']
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Overpass API: {e}")
        return []

def extract_city_from_tags(tags):
    """Extract city name from OSM tags."""
    # Priority order for city identification
    for key in ['addr:city', 'city', 'addr:municipality', 'addr:suburb', 'addr:district']:
        if key in tags:
            return tags[key]
    return None

def parse_bridge_data(elements):
    """Parse OSM elements and extract bridge information."""
    bridges = []
    
    for element in elements:
        # Skip if no tags
        if 'tags' not in element:
            continue
            
        tags = element['tags']
        
        # Extract bridge name
        name = tags.get('name', '')
        if not name:
            # Try alternative name tags
            name = tags.get('bridge:name', tags.get('official_name', ''))
        
        # Skip unnamed bridges that aren't drawbridges or movable bridges
        bridge_type = tags.get('bridge', 'yes')
        bridge_movable = tags.get('bridge:movable', 'no')
        
        # Get coordinates
        if element['type'] == 'way' and 'center' in element:
            lat = element['center']['lat']
            lon = element['center']['lon']
        elif element['type'] == 'node':
            lat = element['lat']
            lon = element['lon']
        else:
            continue
        
        # Extract city
        city = extract_city_from_tags(tags)
        
        # Store the bridge
        bridges.append({
            'osm_id': f"{element['type']}/{element['id']}",
            'name': name,
            'city': city,
            'latitude': lat,
            'longitude': lon,
            'bridge_type': bridge_type,
            'tags': json.dumps(tags)  # Store all tags as JSON
        })
    
    print(f"Parsed {len(bridges)} bridges with valid data")
    return bridges

def insert_bridges(bridges):
    """Insert bridges into database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    new_bridges = 0
    updated_bridges = 0
    
    for bridge in bridges:
        try:
            cursor.execute("""
                INSERT INTO bridges 
                (osm_id, name, city, latitude, longitude, bridge_type, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(osm_id) DO UPDATE SET
                    name = excluded.name,
                    city = excluded.city,
                    bridge_type = excluded.bridge_type,
                    tags = excluded.tags
            """, (
                bridge['osm_id'],
                bridge['name'],
                bridge['city'],
                bridge['latitude'],
                bridge['longitude'],
                bridge['bridge_type'],
                bridge['tags']
            ))
            
            if cursor.rowcount > 0:
                if cursor.lastrowid:
                    new_bridges += 1
                else:
                    updated_bridges += 1
                    
        except Exception as e:
            print(f"Error inserting bridge {bridge['osm_id']}: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    return new_bridges, updated_bridges

def fetch_bridges_for_major_cities():
    """Fetch bridges for major Dutch cities."""
    cities = [
        ("Amsterdam", (4.7, 52.3, 5.1, 52.45)),
        ("Rotterdam", (4.3, 51.85, 4.65, 52.0)),
        ("Den Haag", (4.2, 52.0, 4.45, 52.15)),
        ("Utrecht", (5.0, 52.0, 5.2, 52.15)),
        ("Eindhoven", (5.4, 51.4, 5.55, 51.5)),
        ("Groningen", (6.45, 53.15, 6.65, 53.3)),
        ("Haarlem", (4.55, 52.35, 4.7, 52.42)),
        ("Alkmaar", (4.7, 52.6, 4.8, 52.65)),
        ("Zaandam", (4.75, 52.4, 4.9, 52.5)),
    ]
    
    all_bridges = []
    
    for city_name, bbox in cities:
        print(f"\nFetching bridges for {city_name}...")
        elements = fetch_bridges_from_osm(bbox)
        bridges = parse_bridge_data(elements)
        
        # Add city name if not already set
        for bridge in bridges:
            if not bridge['city']:
                bridge['city'] = city_name
        
        all_bridges.extend(bridges)
        
        # Be nice to the Overpass API
        time.sleep(2)
    
    return all_bridges

def get_database_stats():
    """Get statistics about bridges in database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Total bridges
    cursor.execute("SELECT COUNT(*) FROM bridges")
    total = cursor.fetchone()[0]
    
    # Named bridges
    cursor.execute("SELECT COUNT(*) FROM bridges WHERE name != ''")
    named = cursor.fetchone()[0]
    
    # Bridges by city
    cursor.execute("""
        SELECT city, COUNT(*) as count 
        FROM bridges 
        WHERE city IS NOT NULL
        GROUP BY city 
        ORDER BY count DESC
        LIMIT 10
    """)
    cities = cursor.fetchall()
    
    conn.close()
    
    return total, named, cities

def main():
    """Main function to fetch and store OSM bridge data."""
    print("=== OSM Bridge Data Fetcher ===")
    print(f"Database: {DB_FILE}")
    print()
    
    # Create table
    create_bridges_table()
    
    # Fetch bridges for major cities
    print("Fetching bridges from OpenStreetMap...")
    bridges = fetch_bridges_for_major_cities()
    
    # Remove duplicates based on coordinates
    unique_bridges = {}
    for bridge in bridges:
        key = f"{bridge['latitude']:.5f},{bridge['longitude']:.5f}"
        if key not in unique_bridges or (bridge['name'] and not unique_bridges[key]['name']):
            unique_bridges[key] = bridge
    
    bridges = list(unique_bridges.values())
    print(f"\nTotal unique bridges found: {len(bridges)}")
    
    # Insert into database
    new_count, updated_count = insert_bridges(bridges)
    
    print(f"\n=== Import Results ===")
    print(f"New bridges added: {new_count}")
    print(f"Bridges updated: {updated_count}")
    
    # Show statistics
    total, named, cities = get_database_stats()
    print(f"\n=== Database Statistics ===")
    print(f"Total bridges in database: {total}")
    print(f"Named bridges: {named}")
    print(f"\nBridges by city (top 10):")
    for city, count in cities:
        print(f"  {city}: {count}")

if __name__ == "__main__":
    main()