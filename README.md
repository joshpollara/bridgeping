# Bridge Ping 🌉

Never get stuck at a Dutch bridge again! Bridge Ping tracks bridge openings across the Netherlands and sends you notifications via calendar subscriptions.

## Features

- 🌉 Track 28,000+ bridges across the Netherlands
- ⏰ Real-time bridge opening schedules from NDW (National Data Warehouse)
- 📅 Personal calendar subscriptions (iCal) for your watched bridges
- 🗺️ Interactive map with all bridges
- 🔍 Search by bridge name or address
- 📱 Mobile-responsive design

## Deploy to Render (Free Hosting)

### One-Click Deploy

1. Push your code to GitHub
2. Go to [render.com](https://render.com) and sign up
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Render will auto-detect the `render.yaml` file
6. Click "Create Web Service"

Your app will be live at `https://bridgeping.onrender.com` in ~5 minutes!

### Manual Deploy via Render Dashboard

If you prefer to configure manually:

1. **New Web Service** from your GitHub repo
2. **Runtime**: Docker
3. **Region**: Frankfurt (closest to Netherlands)
4. **Instance**: Free
5. **Add Persistent Disk**:
   - Mount Path: `/app/data`
   - Size: 1 GB
6. **Environment Variables**:
   - `DATABASE_PATH`: `/app/data/bridgeping.db`
   - `JWT_SECRET_KEY`: Click "Generate"
   - `TZ`: `Europe/Amsterdam`

## Quick Start with Docker (Local)

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone <your-repo-url>
cd bridgeping
```

2. Create a `.env` file with a secure JWT secret:
```bash
echo "JWT_SECRET_KEY=$(openssl rand -base64 32)" > .env
```

3. Build and run:
```bash
docker-compose up -d
```

4. Access the app at http://localhost:8000

### Using Docker directly

```bash
# Build the image
docker build -t bridgeping .

# Run the container
docker run -d \
  -p 8000:8000 \
  -v bridgeping_data:/app/data \
  -e JWT_SECRET_KEY="your-secret-key-here" \
  -e TZ="Europe/Amsterdam" \
  --name bridgeping \
  bridgeping
```

## Manual Installation

1. Install Python 3.11+ and SQLite3

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up the database:
```bash
cd app
python3 -c "from webapp.database import init_db; init_db()"
```

4. Run initial data sync:
```bash
python3 bridge_openings_sync.py
python3 fetch_osm_bridges.py
```

5. Start the web app:
```bash
cd webapp
python3 main.py
```

## Usage

1. **Register an account** at http://localhost:8000/register
2. **Search for bridges** using the address search or map
3. **Add bridges** to your watchlist
4. **Subscribe to your calendar** using the personal iCal URL in the dashboard
5. **Get notifications** in your calendar app before bridges open

## Data Sources

- **Bridge Openings**: NDW (Nationale Databank Wegverkeersgegevens)
  - Updated every 6 hours via cron job
  - Real-time opening schedules

- **Bridge Locations**: OpenStreetMap
  - 28,000+ bridges in major Dutch cities
  - Enhanced with street names and neighborhoods

## Environment Variables

- `JWT_SECRET_KEY`: Secret key for authentication (required)
- `DATABASE_PATH`: Path to SQLite database (default: /app/data/bridgeping.db)
- `TZ`: Timezone (default: Europe/Amsterdam)

## Maintenance

The Docker container automatically:
- Syncs bridge opening data every 6 hours
- Creates database backups in the volume
- Restarts on crashes

To manually sync data:
```bash
docker exec bridgeping python3 /app/bridge_openings_sync.py
```

To enhance bridge names (one-time operation):
```bash
docker exec bridgeping python3 /app/enhance_bridge_locations.py
```

## Development

To run in development mode with hot reload:
```bash
cd app/webapp
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## License

MIT License - feel free to use this for any purpose!

## Credits

Built with FastAPI, SQLAlchemy, Leaflet.js, and Bootstrap.
Data from NDW and OpenStreetMap contributors.