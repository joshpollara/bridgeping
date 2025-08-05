from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Optional, List
import json
from datetime import datetime, timezone

from webapp.database import init_db, get_db, Watchlist, WatchlistBridge
from sqlalchemy import text
from webapp.ical_generator import generate_ical_feed
from webapp.name_generator import generate_unique_watchlist_name, is_valid_watchlist_name

app = FastAPI()

# Initialize database
init_db()

# Mount static files
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Templates
templates = Jinja2Templates(directory="webapp/templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request
    })

@app.get("/watchlist", response_class=HTMLResponse)
async def create_watchlist(request: Request):
    """Create a new watchlist with a random name"""
    db = next(get_db())
    
    # Generate unique name
    def check_exists(name):
        return db.query(Watchlist).filter(Watchlist.name == name).first() is not None
    
    watchlist_name = generate_unique_watchlist_name(check_exists)
    
    # Create the watchlist
    new_watchlist = Watchlist(name=watchlist_name)
    db.add(new_watchlist)
    db.commit()
    
    # Redirect to the new watchlist
    return RedirectResponse(url=f"/watchlist/{watchlist_name}", status_code=303)

@app.get("/watchlist/{watchlist_name}", response_class=HTMLResponse)
async def view_watchlist(
    request: Request,
    watchlist_name: str,
    db: Session = Depends(get_db)
):
    """View and manage a specific watchlist"""
    
    # Validate watchlist name format
    if not is_valid_watchlist_name(watchlist_name):
        raise HTTPException(status_code=404, detail="Invalid watchlist name")
    
    # Get or create watchlist
    watchlist = db.query(Watchlist).filter(Watchlist.name == watchlist_name).first()
    if not watchlist:
        # Create new watchlist if it doesn't exist
        watchlist = Watchlist(name=watchlist_name)
        db.add(watchlist)
        db.commit()
        db.refresh(watchlist)
    
    # Get bridges in watchlist
    bridges = db.query(WatchlistBridge).filter(
        WatchlistBridge.watchlist_id == watchlist.id
    ).order_by(WatchlistBridge.created_at.desc()).all()
    
    # Get bridge suggestions
    bridge_suggestions = []
    bridge_id_map = {}
    all_bridge_coords = {}
    
    try:
        # Query for bridges with openings or in major cities
        result = db.execute(text("""
            SELECT DISTINCT b.id, b.name, b.city, b.latitude, b.longitude, 
                   b.street_name, b.water_name, b.neighborhood, b.display_name,
                   CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings
            FROM bridges b
            LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
            WHERE bol.bridge_id IS NOT NULL 
               OR (b.city IN ('Amsterdam', 'Rotterdam', 'Den Haag', 'Utrecht') AND b.name IS NOT NULL)
            ORDER BY has_openings DESC, b.city, b.name
            LIMIT 500
        """))
        
        for row in result:
            # Build the display name
            if row.name:
                if row.city:
                    suggestion = f"{row.name}, {row.city}"
                else:
                    suggestion = f"{row.name}"
            elif row.display_name:
                suggestion = f"{row.display_name}, {row.city}" if row.city else row.display_name
            elif row.street_name and row.water_name:
                suggestion = f"{row.street_name} over {row.water_name}, {row.city}" if row.city else f"{row.street_name} over {row.water_name}"
            elif row.street_name:
                suggestion = f"{row.street_name} Bridge, {row.city}" if row.city else f"{row.street_name} Bridge"
            elif row.city:
                suggestion = f"Bridge in {row.city} ({row.latitude:.5f}, {row.longitude:.5f})"
            else:
                suggestion = f"Bridge at {row.latitude:.5f}, {row.longitude:.5f}"
            
            # Add clock emoji for bridges with scheduled openings
            if row.has_openings:
                suggestion += " ⏰"
            
            bridge_suggestions.append(suggestion)
            bridge_id_map[suggestion] = row.id
            all_bridge_coords[row.id] = {'lat': row.latitude, 'lon': row.longitude}
            
    except Exception as e:
        print(f"Could not fetch bridge suggestions: {e}")
        bridge_suggestions = []
    
    # Get bridge location data for the map
    bridge_map_data = {}
    if bridges:
        bridge_ids = [b.bridge_id for b in bridges if b.bridge_id]
        if bridge_ids:
            placeholders = ','.join([f':id_{i}' for i in range(len(bridge_ids))])
            query = f"""
                SELECT b.id, b.latitude, b.longitude, b.name,
                       CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings
                FROM bridges b
                LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
                WHERE b.id IN ({placeholders})
            """
            params = {f'id_{i}': bridge_id for i, bridge_id in enumerate(bridge_ids)}
            result = db.execute(text(query), params)
            
            for row in result:
                bridge_map_data[row.id] = {
                    'lat': row.latitude,
                    'lon': row.longitude,
                    'name': row.name,
                    'has_openings': bool(row.has_openings)
                }
    
    return templates.TemplateResponse("watchlist.html", {
        "request": request,
        "watchlist": watchlist,
        "bridges": bridges,
        "bridge_suggestions": bridge_suggestions,
        "bridge_id_map": bridge_id_map,
        "bridge_map_data": bridge_map_data,
        "all_bridge_coords": all_bridge_coords
    })

@app.post("/watchlist/{watchlist_name}/add")
async def add_bridge(
    watchlist_name: str,
    bridge_name: str = Form(...),
    bridge_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Add a bridge to a watchlist"""
    
    # Validate watchlist
    watchlist = db.query(Watchlist).filter(Watchlist.name == watchlist_name).first()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    # Validate bridge name
    bridge_name = bridge_name.strip()
    if not bridge_name:
        return RedirectResponse(url=f"/watchlist/{watchlist_name}", status_code=303)
    
    # Check if already in watchlist
    existing = db.query(WatchlistBridge).filter(
        WatchlistBridge.watchlist_id == watchlist.id,
        WatchlistBridge.bridge_name == bridge_name
    ).first()
    
    if not existing:
        # Add to watchlist
        watched_bridge = WatchlistBridge(
            watchlist_id=watchlist.id,
            bridge_name=bridge_name,
            bridge_id=str(bridge_id) if bridge_id else None
        )
        db.add(watched_bridge)
        db.commit()
    
    return RedirectResponse(url=f"/watchlist/{watchlist_name}", status_code=303)

@app.post("/watchlist/{watchlist_name}/remove/{bridge_id}")
async def remove_bridge(
    watchlist_name: str,
    bridge_id: int,
    db: Session = Depends(get_db)
):
    """Remove a bridge from a watchlist"""
    
    # Validate watchlist
    watchlist = db.query(Watchlist).filter(Watchlist.name == watchlist_name).first()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    # Find and remove the bridge
    bridge = db.query(WatchlistBridge).filter(
        WatchlistBridge.id == bridge_id,
        WatchlistBridge.watchlist_id == watchlist.id
    ).first()
    
    if bridge:
        db.delete(bridge)
        db.commit()
    
    return RedirectResponse(url=f"/watchlist/{watchlist_name}", status_code=303)

@app.get("/timeline", response_class=HTMLResponse)
async def timeline_redirect(request: Request):
    """Redirect to create a new watchlist for timeline viewing"""
    return RedirectResponse(url="/watchlist", status_code=303)

@app.get("/timeline/{watchlist_name}", response_class=HTMLResponse)
async def timeline(
    request: Request,
    watchlist_name: str,
    hours: int = Query(72, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Show timeline for a specific watchlist"""
    
    # Get watchlist
    watchlist = db.query(Watchlist).filter(Watchlist.name == watchlist_name).first()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    # Get watched bridges
    watched_bridges = db.query(WatchlistBridge).filter(
        WatchlistBridge.watchlist_id == watchlist.id
    ).all()
    
    if not watched_bridges:
        return templates.TemplateResponse("timeline.html", {
            "request": request,
            "openings": [],
            "hours": hours,
            "user_tz": "Europe/Amsterdam",
            "watchlist": watchlist
        })
    
    # Get bridge IDs for filtering
    bridge_ids = [b.bridge_id for b in watched_bridges if b.bridge_id]
    bridge_names = [b.bridge_name for b in watched_bridges]
    
    # Build query for openings
    query_parts = []
    params = {}
    
    if bridge_ids:
        id_placeholders = ','.join([f':bridge_id_{i}' for i in range(len(bridge_ids))])
        query_parts.append(f"""
            bo.bridge_name IN (
                SELECT DISTINCT bo2.bridge_name 
                FROM bridge_openings bo2
                JOIN bridge_opening_links bol ON (
                    bo2.latitude = bol.latitude AND 
                    bo2.longitude = bol.longitude
                )
                WHERE bol.bridge_id IN ({id_placeholders})
            )
        """)
        for i, bid in enumerate(bridge_ids):
            params[f'bridge_id_{i}'] = bid
    
    if bridge_names:
        name_placeholders = ','.join([f':bridge_name_{i}' for i in range(len(bridge_names))])
        query_parts.append(f"bo.bridge_name IN ({name_placeholders})")
        for i, name in enumerate(bridge_names):
            params[f'bridge_name_{i}'] = name
    
    where_clause = " OR ".join(query_parts) if query_parts else "1=1"
    
    # Query for openings
    query = f"""
        WITH timeline_openings AS (
            SELECT DISTINCT
                bo.bridge_name,
                bo.start_time,
                bo.end_time,
                bo.latitude,
                bo.longitude,
                b.city,
                b.street_name,
                b.water_name,
                b.neighborhood
            FROM bridge_openings bo
            LEFT JOIN bridges b ON (
                ABS(bo.latitude - b.latitude) < 0.001 AND 
                ABS(bo.longitude - b.longitude) < 0.001
            )
            WHERE ({where_clause})
                AND datetime(bo.start_time) >= datetime('now')
                AND datetime(bo.start_time) <= datetime('now', '+{hours} hours')
                AND bo.status = 'active'
        )
        SELECT * FROM timeline_openings
        ORDER BY datetime(start_time), bridge_name
    """
    
    result = db.execute(text(query), params)
    
    openings = []
    for row in result:
        start_dt = datetime.fromisoformat(row.start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(row.end_time.replace('Z', '+00:00'))
        
        opening = {
            'bridge_name': row.bridge_name,
            'start_time': row.start_time,
            'end_time': row.end_time,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'duration_minutes': int((end_dt - start_dt).total_seconds() / 60),
            'city': row.city,
            'street_name': row.street_name,
            'water_name': row.water_name,
            'neighborhood': row.neighborhood,
            'coordinates': {'lat': row.latitude, 'lon': row.longitude}
        }
        openings.append(opening)
    
    return templates.TemplateResponse("timeline.html", {
        "request": request,
        "openings": openings,
        "hours": hours,
        "user_tz": "Europe/Amsterdam",
        "watchlist": watchlist
    })

@app.get("/calendar/watchlist/{watchlist_name}.ics")
async def calendar_feed(watchlist_name: str, db: Session = Depends(get_db)):
    """Generate calendar feed for a watchlist"""
    
    # Validate watchlist name format
    if not is_valid_watchlist_name(watchlist_name):
        raise HTTPException(status_code=404, detail="Invalid watchlist name")
    
    # Get watchlist
    watchlist = db.query(Watchlist).filter(Watchlist.name == watchlist_name).first()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    # Get watched bridges
    watched_bridges = db.query(WatchlistBridge).filter(
        WatchlistBridge.watchlist_id == watchlist.id
    ).all()
    
    if not watched_bridges:
        # Return empty calendar
        ical_content = generate_ical_feed([], f"BridgePing - {watchlist_name}")
        return Response(content=ical_content, media_type="text/calendar")
    
    # Get openings for the next 30 days
    bridge_ids = [b.bridge_id for b in watched_bridges if b.bridge_id]
    bridge_names = [b.bridge_name for b in watched_bridges]
    
    query_parts = []
    params = {}
    
    if bridge_ids:
        id_placeholders = ','.join([f':bridge_id_{i}' for i in range(len(bridge_ids))])
        query_parts.append(f"""
            bridge_name IN (
                SELECT DISTINCT bo.bridge_name 
                FROM bridge_openings bo
                JOIN bridge_opening_links bol ON (
                    bo.latitude = bol.latitude AND 
                    bo.longitude = bol.longitude
                )
                WHERE bol.bridge_id IN ({id_placeholders})
            )
        """)
        for i, bid in enumerate(bridge_ids):
            params[f'bridge_id_{i}'] = bid
    
    if bridge_names:
        name_placeholders = ','.join([f':bridge_name_{i}' for i in range(len(bridge_names))])
        query_parts.append(f"bridge_name IN ({name_placeholders})")
        for i, name in enumerate(bridge_names):
            params[f'bridge_name_{i}'] = name
    
    where_clause = " OR ".join(query_parts) if query_parts else "1=1"
    
    query = f"""
        SELECT bridge_name, start_time, end_time
        FROM bridge_openings
        WHERE ({where_clause})
            AND datetime(start_time) >= datetime('now')
            AND datetime(start_time) <= datetime('now', '+30 days')
            AND status = 'active'
        ORDER BY datetime(start_time)
    """
    
    result = db.execute(text(query), params)
    
    openings = []
    for row in result:
        openings.append({
            'bridge_name': row.bridge_name,
            'start_time': row.start_time,
            'end_time': row.end_time
        })
    
    ical_content = generate_ical_feed(openings, f"BridgePing - {watchlist_name}")
    return Response(content=ical_content, media_type="text/calendar")

# Keep other non-auth routes (bridges, map, etc.)
@app.get("/bridges", response_class=HTMLResponse)
async def bridges_list(request: Request, db: Session = Depends(get_db)):
    """List all bridges grouped by city"""
    result = db.execute(text("""
        SELECT b.id, b.name, b.city, b.street_name, b.water_name, b.neighborhood,
               b.display_name, b.bridge_type, b.latitude, b.longitude,
               CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings,
               COUNT(DISTINCT bo.id) as opening_count
        FROM bridges b
        LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
        LEFT JOIN bridge_openings bo ON (
            bol.latitude = bo.latitude AND 
            bol.longitude = bo.longitude AND
            datetime(bo.start_time) >= datetime('now') AND
            bo.status = 'active'
        )
        WHERE b.name IS NOT NULL OR b.display_name IS NOT NULL
        GROUP BY b.id
        ORDER BY b.city, b.name
    """))
    
    # Group bridges by city
    cities = {}
    for row in result:
        city = row.city or "Unknown"
        if city not in cities:
            cities[city] = []
        
        bridge_info = {
            'id': row.id,
            'name': row.name or row.display_name or f"Bridge at {row.latitude:.5f}, {row.longitude:.5f}",
            'street_name': row.street_name,
            'water_name': row.water_name,
            'neighborhood': row.neighborhood,
            'bridge_type': row.bridge_type,
            'has_openings': bool(row.has_openings),
            'opening_count': row.opening_count,
            'coordinates': {
                'lat': row.latitude,
                'lon': row.longitude
            }
        }
        cities[city].append(bridge_info)
    
    # Sort cities by name, but put "Unknown" at the end
    sorted_cities = sorted(
        cities.items(),
        key=lambda x: (x[0] == "Unknown", x[0])
    )
    
    # Group cities by first letter
    cities_by_letter = {}
    for city_name, city_bridges in sorted_cities:
        if city_name == "Unknown":
            letter = "#"
        else:
            letter = city_name[0].upper()
        
        if letter not in cities_by_letter:
            cities_by_letter[letter] = []
        
        cities_by_letter[letter].append({
            'name': city_name,
            'bridges': city_bridges,
            'bridge_count': len(city_bridges)
        })
    
    return templates.TemplateResponse("bridges.html", {
        "request": request,
        "cities": sorted_cities,
        "cities_by_letter": cities_by_letter,
        "total_bridges": sum(len(bridges) for _, bridges in sorted_cities)
    })

@app.get("/bridges/{city}", response_class=HTMLResponse)
async def bridges_by_city(
    request: Request,
    city: str,
    db: Session = Depends(get_db)
):
    """List bridges in a specific city"""
    result = db.execute(text("""
        SELECT b.id, b.name, b.street_name, b.water_name, b.neighborhood,
               b.display_name, b.bridge_type, b.latitude, b.longitude,
               CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings,
               COUNT(DISTINCT bo.id) as opening_count
        FROM bridges b
        LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
        LEFT JOIN bridge_openings bo ON (
            bol.latitude = bo.latitude AND 
            bol.longitude = bo.longitude AND
            datetime(bo.start_time) >= datetime('now') AND
            bo.status = 'active'
        )
        WHERE b.city = :city AND (b.name IS NOT NULL OR b.display_name IS NOT NULL)
        GROUP BY b.id
        ORDER BY b.name
    """), {"city": city})
    
    bridges = []
    for row in result:
        bridge_info = {
            'id': row.id,
            'name': row.name or row.display_name or f"Bridge at {row.latitude:.5f}, {row.longitude:.5f}",
            'street_name': row.street_name,
            'water_name': row.water_name,
            'neighborhood': row.neighborhood,
            'bridge_type': row.bridge_type,
            'has_openings': bool(row.has_openings),
            'opening_count': row.opening_count,
            'coordinates': {
                'lat': row.latitude,
                'lon': row.longitude
            }
        }
        bridges.append(bridge_info)
    
    return templates.TemplateResponse("city_bridges.html", {
        "request": request,
        "city": city,
        "bridges": bridges
    })

@app.get("/bridge/{bridge_id}", response_class=HTMLResponse)
async def bridge_detail(
    request: Request,
    bridge_id: int,
    db: Session = Depends(get_db)
):
    """Show details for a specific bridge"""
    # Get bridge info
    result = db.execute(text("""
        SELECT b.*, 
               CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings
        FROM bridges b
        LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
        WHERE b.id = :bridge_id
    """), {"bridge_id": bridge_id})
    
    bridge = result.fetchone()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")
    
    # Get upcoming openings
    openings = []
    stats = {
        'total_past_week': 0,
        'upcoming_week': 0,
        'avg_duration': 0
    }
    
    if bridge.has_openings:
        # Get upcoming openings
        result = db.execute(text("""
            SELECT DISTINCT bo.bridge_name, bo.start_time, bo.end_time
            FROM bridge_openings bo
            JOIN bridge_opening_links bol ON (
                bo.latitude = bol.latitude AND 
                bo.longitude = bol.longitude
            )
            WHERE bol.bridge_id = :bridge_id
                AND datetime(bo.start_time) >= datetime('now')
                AND bo.status = 'active'
            ORDER BY datetime(bo.start_time)
            LIMIT 50
        """), {"bridge_id": bridge_id})
        
        for row in result:
            openings.append({
                'bridge_name': row.bridge_name,
                'start_time': row.start_time,
                'end_time': row.end_time
            })
        
        # Calculate statistics
        # Past week openings
        result = db.execute(text("""
            SELECT COUNT(DISTINCT bo.id) as count
            FROM bridge_openings bo
            JOIN bridge_opening_links bol ON (
                bo.latitude = bol.latitude AND 
                bo.longitude = bol.longitude
            )
            WHERE bol.bridge_id = :bridge_id
                AND datetime(bo.start_time) >= datetime('now', '-7 days')
                AND datetime(bo.start_time) < datetime('now')
                AND bo.status = 'active'
        """), {"bridge_id": bridge_id})
        stats['total_past_week'] = result.fetchone().count or 0
        
        # Upcoming week openings
        result = db.execute(text("""
            SELECT COUNT(DISTINCT bo.id) as count
            FROM bridge_openings bo
            JOIN bridge_opening_links bol ON (
                bo.latitude = bol.latitude AND 
                bo.longitude = bol.longitude
            )
            WHERE bol.bridge_id = :bridge_id
                AND datetime(bo.start_time) >= datetime('now')
                AND datetime(bo.start_time) <= datetime('now', '+7 days')
                AND bo.status = 'active'
        """), {"bridge_id": bridge_id})
        stats['upcoming_week'] = result.fetchone().count or 0
        
        # Average duration
        result = db.execute(text("""
            SELECT AVG((julianday(bo.end_time) - julianday(bo.start_time)) * 24 * 60) as avg_duration
            FROM bridge_openings bo
            JOIN bridge_opening_links bol ON (
                bo.latitude = bol.latitude AND 
                bo.longitude = bol.longitude
            )
            WHERE bol.bridge_id = :bridge_id
                AND bo.status = 'active'
                AND bo.end_time IS NOT NULL
        """), {"bridge_id": bridge_id})
        avg_duration = result.fetchone().avg_duration
        stats['avg_duration'] = avg_duration if avg_duration else 0
    
    return templates.TemplateResponse("bridge_detail.html", {
        "request": request,
        "bridge": bridge,
        "openings": openings,
        "stats": stats
    })

@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    """Interactive map view"""
    return templates.TemplateResponse("map.html", {"request": request})

@app.get("/api/bridges/map", response_class=JSONResponse)
async def bridges_map_data(
    bbox: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """API endpoint for map data"""
    query = """
        SELECT b.id, b.name, b.latitude, b.longitude, b.city, 
               b.street_name, b.water_name, b.display_name,
               CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings,
               COUNT(DISTINCT bo.id) as active_openings
        FROM bridges b
        LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
        LEFT JOIN bridge_openings bo ON (
            bol.latitude = bo.latitude AND 
            bol.longitude = bo.longitude AND
            datetime(bo.start_time) >= datetime('now') AND
            datetime(bo.start_time) <= datetime('now', '+7 days') AND
            bo.status = 'active'
        )
    """
    
    params = {}
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(','))
            query += """
                WHERE b.latitude BETWEEN :min_lat AND :max_lat
                AND b.longitude BETWEEN :min_lon AND :max_lon
            """
            params = {
                'min_lat': min_lat,
                'max_lat': max_lat,
                'min_lon': min_lon,
                'max_lon': max_lon
            }
        except:
            pass
    
    query += " GROUP BY b.id"
    
    result = db.execute(text(query), params)
    
    features = []
    for row in result:
        name = row.name or row.display_name
        if not name:
            if row.street_name and row.water_name:
                name = f"{row.street_name} over {row.water_name}"
            elif row.street_name:
                name = f"{row.street_name} Bridge"
            else:
                name = f"Bridge at {row.latitude:.5f}, {row.longitude:.5f}"
        
        feature = {
            "type": "Feature",
            "properties": {
                "id": row.id,
                "name": name,
                "city": row.city,
                "has_openings": bool(row.has_openings),
                "active_openings": row.active_openings
            },
            "geometry": {
                "type": "Point",
                "coordinates": [row.longitude, row.latitude]
            }
        }
        features.append(feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }

@app.get("/calendar/bridge/{bridge_id}.ics")
async def bridge_calendar(bridge_id: int, db: Session = Depends(get_db)):
    """Public calendar feed for a specific bridge"""
    # Get bridge info
    result = db.execute(text("""
        SELECT name, display_name FROM bridges WHERE id = :bridge_id
    """), {"bridge_id": bridge_id})
    
    bridge = result.fetchone()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")
    
    bridge_name = bridge.name or bridge.display_name or f"Bridge {bridge_id}"
    
    # Get openings
    result = db.execute(text("""
        SELECT DISTINCT bo.bridge_name, bo.start_time, bo.end_time
        FROM bridge_openings bo
        JOIN bridge_opening_links bol ON (
            bo.latitude = bol.latitude AND 
            bo.longitude = bol.longitude
        )
        WHERE bol.bridge_id = :bridge_id
            AND datetime(bo.start_time) >= datetime('now')
            AND datetime(bo.start_time) <= datetime('now', '+30 days')
            AND bo.status = 'active'
        ORDER BY datetime(bo.start_time)
    """), {"bridge_id": bridge_id})
    
    openings = []
    for row in result:
        openings.append({
            'bridge_name': row.bridge_name,
            'start_time': row.start_time,
            'end_time': row.end_time
        })
    
    ical_content = generate_ical_feed(openings, f"BridgePing - {bridge_name}")
    return Response(content=ical_content, media_type="text/calendar")

@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request):
    """FAQ page"""
    return templates.TemplateResponse("faq.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)