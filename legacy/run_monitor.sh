#!/bin/bash
# macOS/Linux launcher for Bybit Monitor

set -e

cd "$(dirname "$0")"

echo "Starting Bybit Monitor..."

# Check if Docker is available and user wants to use it
if command -v docker &> /dev/null && [ -f "docker-compose.yml" ]; then
    echo "Docker detected. Starting with Docker Compose..."
    docker-compose up -d bybit-monitor
    echo "Monitor started in background. Use 'docker-compose logs -f' to view logs."
else
    echo "Starting with local Python environment..."
    
    # Activate virtual environment if it exists
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    python start_monitor.py
fi
