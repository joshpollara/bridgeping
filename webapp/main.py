from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Optional
import re
import json
from datetime import datetime, timezone

from webapp.database import init_db, get_db, WatchedBridge
from sqlalchemy import text
from webapp.auth import (
    create_user, 
    authenticate_user, 
    create_access_token,
    get_user_by_email,
    get_current_user,
    get_current_user_required
)
from webapp.ical_generator import generate_ical_feed
import secrets

app = FastAPI()

# Initialize database
init_db()

# Mount static files
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Templates
templates = Jinja2Templates(directory="webapp/templates")

# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": current_user
    })

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    messages = []
    
    # Validate email format
    if not EMAIL_REGEX.match(email):
        messages.append({"type": "danger", "text": "Invalid email format"})
    
    # Check if passwords match
    if password != confirm_password:
        messages.append({"type": "danger", "text": "Passwords do not match"})
    
    # Check password length
    if len(password) < 6:
        messages.append({"type": "danger", "text": "Password must be at least 6 characters long"})
    
    # Check if user already exists
    if get_user_by_email(db, email):
        messages.append({"type": "danger", "text": "Email already registered"})
    
    if messages:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "messages": messages
        })
    
    # Create user
    try:
        create_user(db, email, password)
        response = RedirectResponse(url="/login", status_code=303)
        return response
    except Exception as e:
        messages.append({"type": "danger", "text": "Registration failed. Please try again."})
        return templates.TemplateResponse("register.html", {
            "request": request,
            "messages": messages
        })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "messages": [{"type": "danger", "text": "Invalid email or password"}]
        })
    
    # Create access token
    access_token = create_access_token(data={"sub": user.email})
    
    # Create response and set cookie
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=60 * 60 * 24,  # 24 hours
        path="/"  # Ensure cookie is available for all paths
    )
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    # Generate calendar token if user doesn't have one
    if not current_user.calendar_token:
        token = secrets.token_urlsafe(32)
        db.execute(text("UPDATE users SET calendar_token = :token WHERE id = :id"), 
                  {"token": token, "id": current_user.id})
        db.commit()
        current_user.calendar_token = token
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user
    })

@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist(
    request: Request,
    current_user = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    # Get user's watched bridges ordered by creation date
    bridges = db.query(WatchedBridge).filter(
        WatchedBridge.user_id == current_user.id
    ).order_by(WatchedBridge.created_at.desc()).all()
    
    # Get bridge suggestions with proper IDs
    bridge_suggestions = []
    bridge_id_map = {}  # Maps suggestion text to bridge ID
    all_bridge_coords = {}  # Maps bridge ID to coordinates
    
    try:
        # If user has watched bridges, show those + nearby bridges
        if bridges:
            result = db.execute(text("""
                WITH opening_bridges AS (
                    SELECT DISTINCT b.id, b.name, b.city, b.latitude, b.longitude, 
                           b.street_name, b.water_name, b.neighborhood, b.display_name,
                           1 as has_openings
                    FROM bridges b
                    INNER JOIN bridge_opening_links bol ON b.id = bol.bridge_id
                ),
                watched_locations AS (
                    SELECT DISTINCT b.latitude, b.longitude
                    FROM watched_bridges wb
                    JOIN bridges b ON b.id = wb.bridge_id
                    WHERE wb.user_id = :user_id
                ),
                nearby_bridges AS (
                    SELECT DISTINCT b.id, b.name, b.city, b.latitude, b.longitude,
                           b.street_name, b.water_name, b.neighborhood, b.display_name,
                           0 as has_openings
                    FROM bridges b
                    CROSS JOIN watched_locations wl
                    WHERE b.id NOT IN (SELECT id FROM opening_bridges)
                    AND ABS(b.latitude - wl.latitude) < 0.05
                    AND ABS(b.longitude - wl.longitude) < 0.05
                    LIMIT 500
                )
                SELECT * FROM opening_bridges
                UNION ALL
                SELECT * FROM nearby_bridges
                ORDER BY city, name
            """), {"user_id": current_user.id})
        else:
            # For new users, just show bridges with openings + some Amsterdam bridges
            result = db.execute(text("""
                SELECT DISTINCT b.id, b.name, b.city, b.latitude, b.longitude, 
                       b.street_name, b.water_name, b.neighborhood, b.display_name,
                       CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings
                FROM bridges b
                LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
                WHERE bol.bridge_id IS NOT NULL 
                   OR (b.city = 'Amsterdam' AND b.name IS NOT NULL)
                ORDER BY has_openings DESC, b.city, b.name
                LIMIT 2000
            """))
        
        for row in result:
            # Build the display name
            if row.name:
                if row.city:
                    suggestion = f"{row.name}, {row.city}"
                else:
                    suggestion = f"{row.name}"
            elif row.display_name:
                # Use the enhanced display name
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
            # Create named placeholders for the IN clause
            placeholders = ','.join([f':id_{i}' for i in range(len(bridge_ids))])
            query = f"""
                SELECT b.id, b.latitude, b.longitude, b.name,
                       CASE WHEN bol.bridge_id IS NOT NULL THEN 1 ELSE 0 END as has_openings
                FROM bridges b
                LEFT JOIN bridge_opening_links bol ON b.id = bol.bridge_id
                WHERE b.id IN ({placeholders})
            """
            # Create parameter dict
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
        "user": current_user,
        "bridges": bridges,
        "bridge_suggestions": bridge_suggestions,
        "bridge_id_map": bridge_id_map,
        "bridge_map_data": bridge_map_data,
        "all_bridge_coords": all_bridge_coords
    })

@app.post("/watchlist/add")
async def add_bridge(
    bridge_name: str = Form(...),
    bridge_id: Optional[int] = Form(None),
    current_user = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    # Validate bridge name
    bridge_name = bridge_name.strip()
    if not bridge_name:
        return RedirectResponse(url="/watchlist", status_code=303)
    
    # Try to find bridge_id if not provided
    if not bridge_id:
        # Try to match by name from the bridges table
        result = db.execute(text("""
            SELECT id FROM bridges 
            WHERE name = :name 
            OR (name || ', ' || city) = :name
            OR (name || ' ⏰') = :name
            OR (name || ', ' || city || ' ⏰') = :name
            LIMIT 1
        """), {"name": bridge_name})
        
        row = result.fetchone()
        if row:
            bridge_id = row.id
    
    # Check if user already watches this bridge
    if bridge_id:
        existing = db.query(WatchedBridge).filter(
            WatchedBridge.user_id == current_user.id,
            WatchedBridge.bridge_id == bridge_id
        ).first()
    else:
        existing = db.query(WatchedBridge).filter(
            WatchedBridge.user_id == current_user.id,
            WatchedBridge.bridge_name == bridge_name,
            WatchedBridge.bridge_id == None
        ).first()
    
    if not existing:
        # Add new bridge to watchlist
        new_bridge = WatchedBridge(
            user_id=current_user.id,
            bridge_name=bridge_name,
            bridge_id=bridge_id
        )
        db.add(new_bridge)
        db.commit()
    
    return RedirectResponse(url="/watchlist", status_code=303)

@app.post("/watchlist/remove/{bridge_id}")
async def remove_bridge(
    bridge_id: int,
    current_user = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    # Find the bridge and ensure it belongs to current user
    bridge = db.query(WatchedBridge).filter(
        WatchedBridge.id == bridge_id,
        WatchedBridge.user_id == current_user.id
    ).first()
    
    if bridge:
        db.delete(bridge)
        db.commit()
    
    return RedirectResponse(url="/watchlist", status_code=303)

@app.get("/timeline", response_class=HTMLResponse)
async def timeline(
    request: Request,
    current_user = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    # Get user's watched bridges with bridge_ids
    watched_bridges = db.query(WatchedBridge).filter(
        WatchedBridge.user_id == current_user.id,
        WatchedBridge.bridge_id != None
    ).all()
    
    # Get bridge IDs that have opening links
    bridge_ids = [wb.bridge_id for wb in watched_bridges]
    
    
    if bridge_ids:
        # Get opening events for these bridges
        # First, get the location keys for these bridges
        # Create placeholders for bridge IDs
        placeholders = ','.join([f':id_{i}' for i in range(len(bridge_ids))])
        query = f"""
            SELECT bol.opening_location_key, b.id, b.name, b.display_name, 
                   b.street_name, b.water_name, b.city
            FROM bridge_opening_links bol
            JOIN bridges b ON b.id = bol.bridge_id
            WHERE bol.bridge_id IN ({placeholders})
        """
        params = {f'id_{i}': bridge_id for i, bridge_id in enumerate(bridge_ids)}
        result = db.execute(text(query), params)
        
        bridge_location_map = {}
        for row in result:
            lat, lon = row.opening_location_key.split(',')
            location_key = f"{float(lat):.4f},{float(lon):.4f}"
            bridge_name = row.name or row.display_name or (f"{row.street_name} Bridge" if row.street_name else f"Bridge in {row.city}")
            bridge_location_map[location_key] = {
                'id': row.id,
                'name': bridge_name,
                'city': row.city
            }
        
        # Now get all opening events for these locations
        location_keys = list(bridge_location_map.keys())
        if location_keys:
            placeholders = ','.join([f':loc_{i}' for i in range(len(location_keys))])
            query = f"""
                SELECT 
                    ROUND(latitude, 4) || ',' || ROUND(longitude, 4) as location_key,
                    start_time,
                    end_time,
                    status,
                    created_at
                FROM bridge_openings
                WHERE ROUND(latitude, 4) || ',' || ROUND(longitude, 4) IN ({placeholders})
                ORDER BY start_time DESC
            """
            params = {f'loc_{i}': loc for i, loc in enumerate(location_keys)}
            result = db.execute(text(query), params)
            
            events = []
            unmatched_count = 0
            for row in result:
                bridge_info = bridge_location_map.get(row.location_key)
                if bridge_info:
                    # Parse datetime strings
                    if isinstance(row.start_time, str):
                        # Handle timezone info
                        if row.start_time.endswith('Z'):
                            start_time = datetime.fromisoformat(row.start_time.replace('Z', '+00:00'))
                        elif '+' in row.start_time or row.start_time.endswith('00:00'):
                            start_time = datetime.fromisoformat(row.start_time)
                        else:
                            # Assume UTC if no timezone info
                            start_time = datetime.fromisoformat(row.start_time).replace(tzinfo=timezone.utc)
                    else:
                        start_time = row.start_time
                    
                    if isinstance(row.end_time, str):
                        # Handle timezone info
                        if row.end_time.endswith('Z'):
                            end_time = datetime.fromisoformat(row.end_time.replace('Z', '+00:00'))
                        elif '+' in row.end_time or row.end_time.endswith('00:00'):
                            end_time = datetime.fromisoformat(row.end_time)
                        else:
                            # Assume UTC if no timezone info
                            end_time = datetime.fromisoformat(row.end_time).replace(tzinfo=timezone.utc)
                    else:
                        end_time = row.end_time
                    
                    # Use timezone-aware current time
                    now = datetime.now(timezone.utc)
                    
                    events.append({
                        'bridge_name': bridge_info['name'],
                        'bridge_city': bridge_info['city'],
                        'start_time': start_time,
                        'end_time': end_time,
                        'status': row.status,
                        'is_past': end_time < now,
                        'is_current': start_time <= now <= end_time
                    })
                else:
                    unmatched_count += 1
            
        else:
            events = []
    else:
        events = []
    
    # Split into past and upcoming
    now = datetime.now(timezone.utc)
    past_events = [e for e in events if e['is_past']][:50]  # Limit past events
    current_events = [e for e in events if e['is_current']]
    upcoming_events = [e for e in events if e['start_time'] > now]
    
    return templates.TemplateResponse("timeline.html", {
        "request": request,
        "user": current_user,
        "past_events": past_events,
        "current_events": current_events,
        "upcoming_events": upcoming_events,
        "watched_count": len(watched_bridges)
    })

@app.get("/calendar/feed/{token}.ics")
async def calendar_feed(
    token: str,
    db: Session = Depends(get_db)
):
    # Find user by calendar token
    result = db.execute(text("SELECT id, email FROM users WHERE calendar_token = :token"), 
                       {"token": token})
    user_row = result.fetchone()
    
    if not user_row:
        raise HTTPException(status_code=404, detail="Calendar feed not found")
    
    user_id, user_email = user_row
    
    # Get user's watched bridges
    watched_bridges = db.query(WatchedBridge).filter(
        WatchedBridge.user_id == user_id,
        WatchedBridge.bridge_id != None
    ).all()
    
    bridge_ids = [wb.bridge_id for wb in watched_bridges]
    events = []
    
    if bridge_ids:
        # Get bridge info and their opening locations
        placeholders = ','.join([f':id_{i}' for i in range(len(bridge_ids))])
        query = f"""
            SELECT bol.opening_location_key, b.id, b.name, b.display_name, 
                   b.street_name, b.water_name, b.city, b.latitude, b.longitude
            FROM bridge_opening_links bol
            JOIN bridges b ON b.id = bol.bridge_id
            WHERE bol.bridge_id IN ({placeholders})
        """
        params = {f'id_{i}': bridge_id for i, bridge_id in enumerate(bridge_ids)}
        result = db.execute(text(query), params)
        
        bridge_location_map = {}
        for row in result:
            lat, lon = row.opening_location_key.split(',')
            location_key = f"{float(lat):.4f},{float(lon):.4f}"
            bridge_location_map[location_key] = {
                'id': row.id,
                'name': row.name or row.display_name or (f"{row.street_name} Bridge" if row.street_name else f"Bridge in {row.city}"),
                'city': row.city,
                'latitude': row.latitude,
                'longitude': row.longitude
            }
        
        # Get future opening events
        location_keys = list(bridge_location_map.keys())
        if location_keys:
            placeholders = ','.join([f':loc_{i}' for i in range(len(location_keys))])
            query = f"""
                SELECT 
                    ROUND(latitude, 4) || ',' || ROUND(longitude, 4) as location_key,
                    latitude,
                    longitude,
                    start_time,
                    end_time,
                    status
                FROM bridge_openings
                WHERE ROUND(latitude, 4) || ',' || ROUND(longitude, 4) IN ({placeholders})
                AND datetime(start_time) >= datetime('now')
                ORDER BY start_time
                LIMIT 100
            """
            params = {f'loc_{i}': loc for i, loc in enumerate(location_keys)}
            result = db.execute(text(query), params)
            
            for row in result:
                bridge_info = bridge_location_map.get(row.location_key)
                if bridge_info:
                    # Parse datetime strings
                    if isinstance(row.start_time, str):
                        if row.start_time.endswith('Z'):
                            start_time = datetime.fromisoformat(row.start_time.replace('Z', '+00:00'))
                        elif '+' in row.start_time or row.start_time.endswith('00:00'):
                            start_time = datetime.fromisoformat(row.start_time)
                        else:
                            start_time = datetime.fromisoformat(row.start_time).replace(tzinfo=timezone.utc)
                    else:
                        start_time = row.start_time
                    
                    if isinstance(row.end_time, str):
                        if row.end_time.endswith('Z'):
                            end_time = datetime.fromisoformat(row.end_time.replace('Z', '+00:00'))
                        elif '+' in row.end_time or row.end_time.endswith('00:00'):
                            end_time = datetime.fromisoformat(row.end_time)
                        else:
                            end_time = datetime.fromisoformat(row.end_time).replace(tzinfo=timezone.utc)
                    else:
                        end_time = row.end_time
                    
                    events.append({
                        'bridge_name': bridge_info['name'],
                        'bridge_city': bridge_info['city'],
                        'latitude': row.latitude,
                        'longitude': row.longitude,
                        'location_key': row.location_key,
                        'start_time': start_time,
                        'end_time': end_time,
                        'status': row.status
                    })
    
    # Generate iCal feed
    ical_content = generate_ical_feed(user_email, events)
    
    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": "attachment; filename=bridge-openings.ics",
            "Cache-Control": "no-cache, must-revalidate"
        }
    )

@app.get("/bridges", response_class=HTMLResponse)
async def bridges_list(request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get all cities with bridge counts
    query = """
        SELECT city, COUNT(*) as count 
        FROM bridges 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY city
    """
    result = db.execute(text(query))
    cities = result.fetchall()
    
    # Group cities by first letter for easier navigation
    cities_by_letter = {}
    for city, count in cities:
        first_letter = city[0].upper()
        if first_letter not in cities_by_letter:
            cities_by_letter[first_letter] = []
        cities_by_letter[first_letter].append({'name': city, 'count': count})
    
    return templates.TemplateResponse("bridges.html", {
        "request": request,
        "user": current_user,
        "cities_by_letter": cities_by_letter
    })

@app.get("/bridges/{city}", response_class=HTMLResponse)
async def bridges_by_city(city: str, request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get all bridges in the specified city
    query = """
        SELECT id, name, display_name, street_name, water_name, neighborhood, latitude, longitude
        FROM bridges 
        WHERE city = :city 
        ORDER BY name, street_name
    """
    result = db.execute(text(query), {"city": city})
    bridges = result.fetchall()
    
    # Process bridges to create display names
    bridge_list = []
    for bridge in bridges:
        display_name = bridge.name or bridge.display_name or (f"{bridge.street_name} Bridge" if bridge.street_name else "Unknown Bridge")
        bridge_list.append({
            'id': bridge.id,
            'name': display_name,
            'street_name': bridge.street_name,
            'water_name': bridge.water_name,
            'neighborhood': bridge.neighborhood,
            'latitude': bridge.latitude,
            'longitude': bridge.longitude
        })
    
    return templates.TemplateResponse("bridges_city.html", {
        "request": request,
        "user": current_user,
        "city": city,
        "bridges": bridge_list
    })

@app.get("/calendar/bridge/{bridge_id}.ics")
async def bridge_calendar_feed(
    bridge_id: int,
    db: Session = Depends(get_db)
):
    # Get bridge info
    result = db.execute(text("""
        SELECT id, name, display_name, street_name, water_name, city, latitude, longitude
        FROM bridges 
        WHERE id = :bridge_id
    """), {"bridge_id": bridge_id})
    bridge = result.fetchone()
    
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")
    
    bridge_name = bridge.name or bridge.display_name or (f"{bridge.street_name} Bridge" if bridge.street_name else f"Bridge in {bridge.city}")
    
    # Get bridge opening locations
    result = db.execute(text("""
        SELECT opening_location_key
        FROM bridge_opening_links
        WHERE bridge_id = :bridge_id
    """), {"bridge_id": bridge_id})
    
    location_keys = []
    for row in result:
        lat, lon = row.opening_location_key.split(',')
        location_key = f"{float(lat):.4f},{float(lon):.4f}"
        location_keys.append(location_key)
    
    events = []
    if location_keys:
        # Get all opening events for this bridge
        placeholders = ','.join([f':loc_{i}' for i in range(len(location_keys))])
        query = f"""
            SELECT latitude, longitude, start_time, end_time, status,
                   ROUND(latitude, 4) || ',' || ROUND(longitude, 4) as location_key
            FROM bridge_openings
            WHERE ROUND(latitude, 4) || ',' || ROUND(longitude, 4) IN ({placeholders})
            AND start_time >= datetime('now', '-7 days')
            ORDER BY start_time
        """
        params = {f'loc_{i}': loc for i, loc in enumerate(location_keys)}
        result = db.execute(text(query), params)
        
        for row in result:
            # Parse datetime strings
            if isinstance(row.start_time, str):
                if row.start_time.endswith('Z'):
                    start_time = datetime.fromisoformat(row.start_time.replace('Z', '+00:00'))
                elif '+' in row.start_time or row.start_time.endswith('00:00'):
                    start_time = datetime.fromisoformat(row.start_time)
                else:
                    start_time = datetime.fromisoformat(row.start_time).replace(tzinfo=timezone.utc)
            else:
                start_time = row.start_time
            
            if isinstance(row.end_time, str):
                if row.end_time.endswith('Z'):
                    end_time = datetime.fromisoformat(row.end_time.replace('Z', '+00:00'))
                elif '+' in row.end_time or row.end_time.endswith('00:00'):
                    end_time = datetime.fromisoformat(row.end_time)
                else:
                    end_time = datetime.fromisoformat(row.end_time).replace(tzinfo=timezone.utc)
            else:
                end_time = row.end_time
            
            events.append({
                'bridge_name': bridge_name,
                'bridge_city': bridge.city,
                'latitude': row.latitude,
                'longitude': row.longitude,
                'location_key': row.location_key,
                'start_time': start_time,
                'end_time': end_time,
                'status': row.status
            })
    
    # Generate iCal feed for this specific bridge
    ical_content = generate_ical_feed(f"{bridge_name} - {bridge.city}", events)
    
    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f"attachment; filename={bridge_id}-bridge-openings.ics",
            "Cache-Control": "no-cache, must-revalidate"
        }
    )

@app.get("/bridge/{bridge_id}", response_class=HTMLResponse)
async def bridge_detail(bridge_id: int, request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get bridge info
    result = db.execute(text("""
        SELECT id, name, display_name, street_name, water_name, city, 
               neighborhood, latitude, longitude
        FROM bridges 
        WHERE id = :bridge_id
    """), {"bridge_id": bridge_id})
    bridge = result.fetchone()
    
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")
    
    bridge_name = bridge.name or bridge.display_name or (f"{bridge.street_name} Bridge" if bridge.street_name else f"Bridge in {bridge.city}")
    
    # Get recent and upcoming openings
    result = db.execute(text("""
        SELECT bo.start_time, bo.end_time, bo.status, bo.latitude, bo.longitude
        FROM bridge_openings bo
        JOIN bridge_opening_links bol ON 
            ROUND(bo.latitude, 4) || ',' || ROUND(bo.longitude, 4) = bol.opening_location_key
        WHERE bol.bridge_id = :bridge_id
        AND bo.start_time >= datetime('now', '-7 days')
        ORDER BY bo.start_time
        LIMIT 100
    """), {"bridge_id": bridge_id})
    
    openings = []
    for row in result:
        # Parse datetime strings
        if isinstance(row.start_time, str):
            if row.start_time.endswith('Z'):
                start_time = datetime.fromisoformat(row.start_time.replace('Z', '+00:00'))
            elif '+' in row.start_time or row.start_time.endswith('00:00'):
                start_time = datetime.fromisoformat(row.start_time)
            else:
                start_time = datetime.fromisoformat(row.start_time).replace(tzinfo=timezone.utc)
        else:
            start_time = row.start_time
            
        if isinstance(row.end_time, str):
            if row.end_time.endswith('Z'):
                end_time = datetime.fromisoformat(row.end_time.replace('Z', '+00:00'))
            elif '+' in row.end_time or row.end_time.endswith('00:00'):
                end_time = datetime.fromisoformat(row.end_time)
            else:
                end_time = datetime.fromisoformat(row.end_time).replace(tzinfo=timezone.utc)
        else:
            end_time = row.end_time
        
        openings.append({
            'start_time': start_time,
            'end_time': end_time,
            'status': row.status,
            'duration_minutes': int((end_time - start_time).total_seconds() / 60)
        })
    
    # Calculate statistics
    past_openings = [o for o in openings if o['start_time'] < datetime.now(timezone.utc)]
    future_openings = [o for o in openings if o['start_time'] >= datetime.now(timezone.utc)]
    
    stats = {
        'total_past_week': len(past_openings),
        'upcoming_week': len(future_openings),
        'avg_duration': sum(o['duration_minutes'] for o in past_openings) / len(past_openings) if past_openings else 0
    }
    
    # Check if user has this bridge in watchlist
    is_watched = False
    if current_user:
        watched = db.query(WatchedBridge).filter(
            WatchedBridge.user_id == current_user.id,
            WatchedBridge.bridge_id == bridge_id
        ).first()
        is_watched = watched is not None
    
    return templates.TemplateResponse("bridge_detail.html", {
        "request": request,
        "user": current_user,
        "bridge": {
            'id': bridge.id,
            'name': bridge_name,
            'street_name': bridge.street_name,
            'water_name': bridge.water_name,
            'city': bridge.city,
            'neighborhood': bridge.neighborhood,
            'latitude': bridge.latitude,
            'longitude': bridge.longitude
        },
        "stats": stats,
        "openings": openings,
        "is_watched": is_watched
    })

@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    return templates.TemplateResponse("map.html", {
        "request": request,
        "user": current_user
    })

@app.get("/api/bridges/map", response_class=JSONResponse)
async def api_bridges_map(
    bounds: str = Query(None, description="Map bounds as 'south,west,north,east'"),
    db: Session = Depends(get_db)
):
    # Parse bounds if provided
    if bounds:
        try:
            south, west, north, east = map(float, bounds.split(','))
            query = text("""
                SELECT id, name, display_name, street_name, city, latitude, longitude,
                       (SELECT COUNT(*) FROM bridge_opening_links WHERE bridge_id = bridges.id) as opening_count
                FROM bridges
                WHERE latitude BETWEEN :south AND :north
                AND longitude BETWEEN :west AND :east
                LIMIT 1000
            """)
            result = db.execute(query, {
                "south": south, "north": north,
                "west": west, "east": east
            })
        except:
            raise HTTPException(status_code=400, detail="Invalid bounds format")
    else:
        # Return major cities with aggregated bridge counts for initial view
        query = text("""
            SELECT city, 
                   AVG(latitude) as latitude, 
                   AVG(longitude) as longitude,
                   COUNT(*) as count
            FROM bridges
            WHERE city IN (
                SELECT city FROM bridges 
                WHERE city IS NOT NULL 
                GROUP BY city 
                HAVING COUNT(*) > 50
                ORDER BY COUNT(*) DESC
                LIMIT 20
            )
            GROUP BY city
        """)
        result = db.execute(query)
        
        cities = []
        for row in result:
            cities.append({
                "type": "city",
                "name": row.city,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "count": row.count
            })
        return {"type": "cities", "data": cities}
    
    # Return individual bridges
    bridges = []
    for row in result:
        bridge_name = row.name or row.display_name or (f"{row.street_name} Bridge" if row.street_name else f"Bridge in {row.city}")
        bridges.append({
            "id": row.id,
            "name": bridge_name,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "city": row.city,
            "has_openings": row.opening_count > 0
        })
    
    return {"type": "bridges", "data": bridges}

@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request, current_user = Depends(get_current_user)):
    return templates.TemplateResponse("faq.html", {
        "request": request,
        "user": current_user
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.main:app", host="0.0.0.0", port=8000, reload=True)