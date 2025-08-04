# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BridgePing is a web application that tracks and monitors bridge openings in the Netherlands. It collects real-time data from the Dutch National Data Warehouse (NDW), allows users to create watchlists, and provides calendar feeds for bridge opening schedules.

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application locally
python webapp/main.py
# Application will be available at http://localhost:8000
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# Or run Docker manually
docker build -t bridgeping .
docker run -p 8000:8000 -v $(pwd)/data:/app/data bridgeping
```

### Database Commands
```bash
# Initialize database
python bin/init-db.py

# Run migration scripts (when needed)
python webapp/migrate_bridge_data.py
```

### Deployment
```bash
# Deploy to Fly.io
fly deploy
```

## Architecture Overview

### Tech Stack
- **Backend**: FastAPI with Uvicorn server
- **Database**: SQLite with SQLAlchemy ORM (hybrid approach)
- **Frontend**: Jinja2 templates with Bootstrap 5
- **Authentication**: JWT tokens in HTTP-only cookies
- **Deployment**: Docker containers on Fly.io

### Key Components

1. **Web Application** (`/webapp/`)
   - `main.py`: FastAPI routes and application logic
   - `auth.py`: JWT authentication system
   - `database.py`: SQLAlchemy models and database setup
   - `templates/`: Jinja2 HTML templates
   - `static/`: CSS, JavaScript, and other assets

2. **Data Synchronization** (`/bin/`)
   - `bridge_openings_sync.py`: Syncs opening data from NDW XML feed (runs every 6 hours)
   - `fetch_osm_bridges.py`: Updates bridge metadata from OpenStreetMap (runs weekly)
   - `enhance_bridge_locations.py`: Enriches bridge location data (runs weekly)

3. **Database Schema**
   - **SQLAlchemy Models**: `User`, `WatchedBridge`
   - **Raw SQL Tables**: `bridges`, `bridge_openings`, `bridge_opening_links`
   - Uses proper indexes on coordinates, timestamps, and foreign keys

### Authentication Flow
- Users register with email/password
- Passwords hashed with bcrypt
- JWT tokens generated on login, stored in HTTP-only cookies
- Token expiry: 24 hours
- Dependencies: `get_current_user` (optional), `get_current_user_required` (mandatory)

### Data Flow
1. NDW XML data → `bridge_openings_sync.py` → `bridge_openings` table
2. OpenStreetMap → `fetch_osm_bridges.py` → `bridges` table
3. User interactions → FastAPI routes → SQLAlchemy/Raw SQL → Database

### API Endpoints
- `GET/POST /register` - User registration
- `GET/POST /login` - Authentication
- `GET /dashboard` - User dashboard
- `GET /watchlist` - Manage watched bridges
- `POST /watchlist/add` - Add bridge to watchlist
- `POST /watchlist/remove/{id}` - Remove from watchlist
- `GET /timeline` - View bridge openings
- `GET /calendar/feed/{token}.ics` - iCal calendar feed

### Testing
Currently minimal test infrastructure. One test script exists: `webapp/timeline_test.py`

### Environment Variables
- `DATABASE_PATH`: SQLite database location (default: `/app/data/bridgeping.db`)
- `JWT_SECRET_KEY`: Secret for JWT tokens
- `TZ`: Timezone (set to `Europe/Amsterdam`)

### Important Patterns
- **Dependency Injection**: Uses FastAPI's `Depends()` for database sessions and auth
- **POST-Redirect-GET**: Returns 303 redirects after form submissions
- **Idempotent Sync**: Uses `INSERT OR IGNORE` for data deduplication
- **Complex Queries**: Uses CTEs for efficient timeline queries with location filtering
- **Error Handling**: User-friendly form validation messages

### Security Considerations
- Parameterized SQL queries prevent injection
- Passwords hashed with bcrypt
- JWT tokens in HTTP-only cookies
- No sensitive data in version control
- HTTPS enforcement via Fly.io configuration