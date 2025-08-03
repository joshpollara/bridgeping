FROM python:3.11-slim

# Install system dependencies including cron
RUN apt-get update && apt-get install -y \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

# Create data directory
RUN mkdir -p /app/data

# Setup cron jobs
RUN echo "0 */6 * * * cd /app && /usr/local/bin/python /app/bin/bridge_openings_sync.py >> /var/log/cron.log 2>&1" > /etc/cron.d/bridge-sync && \
    echo "0 2 * * 0 cd /app && /usr/local/bin/python /app/bin/fetch_osm_bridges.py >> /var/log/cron.log 2>&1" >> /etc/cron.d/bridge-sync && \
    echo "0 3 * * 0 cd /app && /usr/local/bin/python /app/bin/enhance_bridge_locations.py >> /var/log/cron.log 2>&1" >> /etc/cron.d/bridge-sync && \
    chmod 0644 /etc/cron.d/bridge-sync && \
    crontab /etc/cron.d/bridge-sync && \
    touch /var/log/cron.log

# Expose port
EXPOSE 8000

# Volume for persistent data
VOLUME ["/app/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["/app/bin/start.sh"]
