# BridgePing

Real-time bridge opening notifications for the Netherlands. Track when bridges open and never miss your commute again.

## Features

- 🌉 **Real-time Bridge Monitoring** - Live data from the Dutch National Data Warehouse (NDW)
- 👤 **Personal Watchlists** - Track bridges that matter to you
- 📅 **Calendar Integration** - Export bridge openings to your calendar (iCal format)
- 📍 **Location-based Search** - Find bridges near you
- 📊 **Timeline View** - See past, current, and upcoming bridge openings
- 🔔 **Smart Notifications** - Get alerts for your watched bridges (coming soon)

## Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/bridgeping.git
cd bridgeping

# Run with Docker Compose
docker-compose up --build

# Visit http://localhost:8000
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize the database
python bin/init-db.py

# Run the application
python webapp/main.py

# Visit http://localhost:8000
```

## Architecture

BridgePing uses:
- **FastAPI** - Modern Python web framework
- **SQLite** - Lightweight database for bridge and user data
- **Bootstrap 5** - Responsive UI design
- **Docker** - Containerized deployment

Data is synchronized from:
- **NDW (Nationale Databank Wegverkeersgegevens)** - Real-time bridge opening events
- **OpenStreetMap** - Bridge locations and metadata

## Deployment

The application is designed to run on [Fly.io](https://fly.io):

```bash
# Deploy to production
fly deploy
```

## Data Sources

- Bridge opening events: [NDW Open Data](https://www.ndw.nu/onderwerpen/open-data/)
- Bridge locations: [OpenStreetMap](https://www.openstreetmap.org/)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [MIT License](LICENSE).