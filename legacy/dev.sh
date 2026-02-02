#!/bin/bash
# Development helper script for cross-platform development

set -e

cd "$(dirname "$0")"

show_help() {
    cat << EOF
Bybit Monitor Development Helper

Usage: ./dev.sh [command]

Commands:
    start       Start the monitor in Docker
    stop        Stop the monitor
    restart     Restart the monitor
    logs        View monitor logs (follow mode)
    shell       Open a shell in the container
    build       Build/rebuild Docker image
    pnl         Generate PnL report
    clean       Stop and remove containers
    status      Show container status
    
Examples:
    ./dev.sh start
    ./dev.sh logs
    ./dev.sh shell
EOF
}

case "$1" in
    start)
        echo "Starting Bybit Monitor..."
        docker-compose up -d bybit-monitor
        echo "Monitor started. Use './dev.sh logs' to view output."
        ;;
    stop)
        echo "Stopping monitor..."
        docker-compose stop bybit-monitor
        ;;
    restart)
        echo "Restarting monitor..."
        docker-compose restart bybit-monitor
        ;;
    logs)
        echo "Viewing logs (Ctrl+C to exit)..."
        docker-compose logs -f bybit-monitor
        ;;
    shell)
        echo "Opening shell in container..."
        docker-compose exec bybit-monitor /bin/bash
        ;;
    build)
        echo "Building Docker image..."
        docker-compose build
        ;;
    pnl)
        echo "Generating PnL report..."
        docker-compose run --rm pnl-report
        ;;
    clean)
        echo "Cleaning up containers..."
        docker-compose down
        ;;
    status)
        docker-compose ps
        ;;
    *)
        show_help
        ;;
esac
