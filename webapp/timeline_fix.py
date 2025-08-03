# Fixed timeline query that ensures only watched bridges are shown

def get_timeline_events(db, user_id):
    """Get timeline events for a user's watched bridges."""
    
    # Step 1: Get watched bridges that have opening data
    query = """
        SELECT DISTINCT 
            wb.bridge_id,
            b.name as bridge_name,
            b.city,
            bol.opening_location_key,
            ROUND(bol.latitude, 4) as lat_round,
            ROUND(bol.longitude, 4) as lon_round
        FROM watched_bridges wb
        JOIN bridges b ON b.id = wb.bridge_id
        JOIN bridge_opening_links bol ON bol.bridge_id = b.id
        WHERE wb.user_id = :user_id
        AND wb.bridge_id IS NOT NULL
    """
    
    result = db.execute(text(query), {"user_id": user_id})
    
    # Build mapping of rounded coordinates to bridge info
    coord_to_bridge = {}
    for row in result:
        coord_key = f"{row.lat_round},{row.lon_round}"
        coord_to_bridge[coord_key] = {
            'id': row.bridge_id,
            'name': row.bridge_name,
            'city': row.city
        }
    
    if not coord_to_bridge:
        return []
    
    # Step 2: Get openings ONLY for these specific coordinates
    coord_keys = list(coord_to_bridge.keys())
    placeholders = ','.join([f':coord_{i}' for i in range(len(coord_keys))])
    
    query = f"""
        SELECT 
            ROUND(latitude, 4) || ',' || ROUND(longitude, 4) as coord_key,
            latitude,
            longitude,
            start_time,
            end_time,
            status
        FROM bridge_openings
        WHERE ROUND(latitude, 4) || ',' || ROUND(longitude, 4) IN ({placeholders})
        AND datetime(start_time) >= datetime('now')
        ORDER BY start_time
    """
    
    params = {f'coord_{i}': coord for i, coord in enumerate(coord_keys)}
    result = db.execute(text(query), params)
    
    events = []
    for row in result:
        bridge_info = coord_to_bridge.get(row.coord_key)
        if bridge_info:  # This should always be true given our query
            events.append({
                'bridge_id': bridge_info['id'],
                'bridge_name': bridge_info['name'],
                'bridge_city': bridge_info['city'],
                'latitude': row.latitude,
                'longitude': row.longitude,
                'start_time': parse_datetime(row.start_time),
                'end_time': parse_datetime(row.end_time),
                'status': row.status
            })
    
    return events