#!/usr/bin/env python3
import urllib.request
import gzip
import xml.etree.ElementTree as ET
import sqlite3
from datetime import datetime
import os
import sys

DB_FILE = os.environ.get('DATABASE_PATH', '/app/data/bridgeping.db')
URL = "https://opendata.ndw.nu/brugopeningen.xml.gz"
TEMP_FILE = "brugopeningen.xml.gz"

def create_database():
    """Create the SQLite database and tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create table for bridge openings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridge_openings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT UNIQUE NOT NULL,
            bridge_name TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            creation_time TIMESTAMP NOT NULL,
            version_time TIMESTAMP NOT NULL,
            source TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index on record_id for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_record_id ON bridge_openings(record_id)
    """)
    
    # Create index on start_time for time-based queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_start_time ON bridge_openings(start_time)
    """)
    
    conn.commit()
    conn.close()
    print("Database schema created/verified.")

def download_and_decompress():
    """Download the XML file and decompress it."""
    print(f"Downloading from {URL}...")
    try:
        urllib.request.urlretrieve(URL, TEMP_FILE)
        print("Download complete.")
        
        print("Decompressing...")
        with gzip.open(TEMP_FILE, 'rb') as f:
            xml_content = f.read()
        
        # Clean up temp file
        os.remove(TEMP_FILE)
        print("Decompression complete.")
        return xml_content
    except Exception as e:
        print(f"Error downloading/decompressing: {e}")
        sys.exit(1)

def parse_iso_timestamp(timestamp_str):
    """Parse ISO format timestamp string to datetime object."""
    # Remove microseconds if present (keep only up to seconds)
    if '.' in timestamp_str:
        timestamp_str = timestamp_str.split('.')[0] + 'Z'
    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

def parse_bridge_openings(xml_content):
    """Parse the XML and extract bridge opening records."""
    print("Parsing XML...")
    root = ET.fromstring(xml_content)
    
    # Define namespace
    ns = {'d2': 'http://datex2.eu/schema/2/2_0'}
    
    # Find all situationRecord elements
    situation_records = root.findall('.//d2:situationRecord', ns)
    print(f"Found {len(situation_records)} situation records.")
    
    bridge_openings = []
    
    for record in situation_records:
        try:
            # Extract record ID and version
            record_id = record.get('id')
            version = record.get('version', '1')
            
            # Combine ID and version for unique identification
            unique_record_id = f"{record_id}_v{version}"
            
            # Extract timestamps
            creation_time = record.find('d2:situationRecordCreationTime', ns).text
            version_time = record.find('d2:situationRecordVersionTime', ns).text
            
            # Extract validity period
            validity = record.find('d2:validity', ns)
            validity_spec = validity.find('d2:validityTimeSpecification', ns)
            start_time = validity_spec.find('d2:overallStartTime', ns).text
            end_time = validity_spec.find('d2:overallEndTime', ns).text
            
            # Extract location
            location = record.find('.//d2:pointCoordinates', ns)
            latitude = float(location.find('d2:latitude', ns).text)
            longitude = float(location.find('d2:longitude', ns).text)
            
            # Extract source
            source_elem = record.find('.//d2:sourceName/d2:values/d2:value', ns)
            source = source_elem.text if source_elem is not None else 'Unknown'
            
            # Extract status
            status = record.find('d2:operatorActionStatus', ns)
            status_text = status.text if status is not None else 'unknown'
            
            # Extract management type (should be bridgeSwingInOperation)
            mgmt_type = record.find('d2:generalNetworkManagementType', ns)
            if mgmt_type is not None and mgmt_type.text == 'bridgeSwingInOperation':
                bridge_openings.append({
                    'record_id': unique_record_id,
                    'bridge_name': None,  # Not provided in the data
                    'latitude': latitude,
                    'longitude': longitude,
                    'start_time': parse_iso_timestamp(start_time),
                    'end_time': parse_iso_timestamp(end_time),
                    'creation_time': parse_iso_timestamp(creation_time),
                    'version_time': parse_iso_timestamp(version_time),
                    'source': source,
                    'status': status_text
                })
        except Exception as e:
            print(f"Error parsing record {record.get('id', 'unknown')}: {e}")
            continue
    
    print(f"Successfully parsed {len(bridge_openings)} bridge opening records.")
    return bridge_openings

def insert_bridge_openings(bridge_openings):
    """Insert bridge openings into database with deduplication."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    new_records = 0
    existing_records = 0
    
    for opening in bridge_openings:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO bridge_openings 
                (record_id, bridge_name, latitude, longitude, start_time, end_time, 
                 creation_time, version_time, source, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                opening['record_id'],
                opening['bridge_name'],
                opening['latitude'],
                opening['longitude'],
                opening['start_time'],
                opening['end_time'],
                opening['creation_time'],
                opening['version_time'],
                opening['source'],
                opening['status']
            ))
            
            if cursor.rowcount > 0:
                new_records += 1
            else:
                existing_records += 1
                
        except Exception as e:
            print(f"Error inserting record {opening['record_id']}: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    return new_records, existing_records

def get_database_stats():
    """Get statistics about the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Total records
    cursor.execute("SELECT COUNT(*) FROM bridge_openings")
    total_records = cursor.fetchone()[0]
    
    # Records by source
    cursor.execute("""
        SELECT source, COUNT(*) as count 
        FROM bridge_openings 
        GROUP BY source 
        ORDER BY count DESC
    """)
    sources = cursor.fetchall()
    
    # Upcoming openings (future from now)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM bridge_openings 
        WHERE start_time > datetime('now')
    """)
    upcoming = cursor.fetchone()[0]
    
    conn.close()
    
    return total_records, sources, upcoming

def main():
    """Main function to orchestrate the bridge opening sync."""
    print("=== Bridge Openings Sync ===")
    print(f"Database: {DB_FILE}")
    print(f"Source: {URL}")
    print()
    
    # Create database if needed
    create_database()
    
    # Download and decompress
    xml_content = download_and_decompress()
    
    # Parse bridge openings
    bridge_openings = parse_bridge_openings(xml_content)
    
    # Insert into database
    new_records, existing_records = insert_bridge_openings(bridge_openings)
    
    # Print results
    print("\n=== Sync Results ===")
    print(f"New events added: {new_records}")
    print(f"Existing events skipped: {existing_records}")
    print(f"Total events processed: {new_records + existing_records}")
    
    # Get and print database statistics
    total_records, sources, upcoming = get_database_stats()
    print(f"\n=== Database Statistics ===")
    print(f"Total records in database: {total_records}")
    print(f"Upcoming bridge openings: {upcoming}")
    print(f"\nRecords by source:")
    for source, count in sources:
        print(f"  {source}: {count}")

if __name__ == "__main__":
    main()
