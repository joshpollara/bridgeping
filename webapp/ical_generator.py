from datetime import datetime, timedelta, timezone
from typing import List, Dict
import hashlib

def generate_ical_feed(user_email: str, events: List[Dict]) -> str:
    """Generate iCalendar feed for bridge opening events."""
    
    # iCal header
    ical = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BridgePing//Bridge Opening Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Bridge Openings - {user_email}",
        "X-WR-CALDESC:Scheduled bridge openings for your watched bridges",
        "X-WR-TIMEZONE:Europe/Amsterdam",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",  # Refresh every hour
    ]
    
    # Add timezone definition for Amsterdam
    ical.extend([
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Amsterdam",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ])
    
    # Add events
    for event in events:
        # Generate unique ID for this event
        uid_string = f"{event['bridge_name']}-{event['start_time']}-{event['location_key']}"
        uid = hashlib.md5(uid_string.encode()).hexdigest()
        
        # Format times for iCal
        dtstart = format_datetime_for_ical(event['start_time'])
        dtend = format_datetime_for_ical(event['end_time'])
        dtstamp = format_datetime_for_ical(datetime.now(timezone.utc))
        
        # Calculate duration
        duration = event['end_time'] - event['start_time']
        duration_minutes = int(duration.total_seconds() / 60)
        
        # Build event
        ical.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}@bridgeping.app",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:🌉 {event['bridge_name']} Opening",
            f"DESCRIPTION:Bridge scheduled to open for {duration_minutes} minutes.\\n"
            f"Location: {event['bridge_city'] or 'Unknown'}\\n"
            f"Status: {event['status']}\\n\\n"
            f"Plan your route accordingly to avoid delays.",
            f"LOCATION:{event['bridge_name']}, {event['bridge_city'] or 'Netherlands'}",
            f"GEO:{event['latitude']};{event['longitude']}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",  # Show as busy
            "BEGIN:VALARM",  # 15 minute reminder
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Bridge opening in 15 minutes: {event['bridge_name']}",
            "END:VALARM",
            "END:VEVENT",
        ])
    
    # iCal footer
    ical.append("END:VCALENDAR")
    
    # Join with CRLF line endings as per iCal spec
    return "\r\n".join(ical)

def format_datetime_for_ical(dt: datetime) -> str:
    """Format datetime for iCalendar (UTC)."""
    if dt.tzinfo is None:
        # Assume UTC if no timezone
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to UTC and format
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")