#!/bin/bash
# macOS/Linux PnL Report Generator

set -e

cd "$(dirname "$0")"

echo "Generating PnL Report..."

# Check if Docker is available
if command -v docker &> /dev/null && [ -f "docker-compose.yml" ]; then
    echo "Running with Docker..."
    docker-compose run --rm pnl-report
else
    echo "Running with local Python environment..."
    
    # Activate virtual environment if it exists
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    python manual_report.py
fi

echo "Report generation complete!"
