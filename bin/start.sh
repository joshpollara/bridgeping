#!/bin/bash

# Initialize database
python /app/bin/init-db.py

# Start cron in background
service cron start

# Start the web application
exec python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8000
