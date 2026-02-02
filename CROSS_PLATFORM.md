# Cross-Platform Development Guide

This project supports seamless development on both **Windows 11** and **macOS (M2)**.

## Quick Start

### Windows 11

**Option 1: Docker (Recommended for consistency)**
```powershell
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**Option 2: Native Python**
```powershell
# Use existing batch files
run_monitor.bat
check_pnl.bat
```

### macOS (M2)

**Option 1: Docker (Recommended for consistency)**
```bash
# Make scripts executable (first time only)
chmod +x *.sh

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**Option 2: Native Python**
```bash
# Use shell scripts
./run_monitor.sh
./check_pnl.sh
```

## Development Helper (macOS/Linux)

The `dev.sh` script provides convenient commands:

```bash
./dev.sh start      # Start monitor
./dev.sh logs       # View logs
./dev.sh shell      # Open container shell
./dev.sh pnl        # Generate PnL report
./dev.sh stop       # Stop monitor
./dev.sh clean      # Remove containers
```

## Environment Setup

### First Time Setup

1. **Copy environment file**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your credentials**
   - Bybit API keys
   - Notion token and database ID
   - Discord webhook URLs

3. **Choose your approach**
   - **Docker**: No additional setup needed
   - **Native Python**: Create virtual environment
     ```bash
     # Windows
     python -m venv venv
     venv\Scripts\activate
     pip install -r requirements.txt

     # macOS/Linux
     python3 -m venv venv
     source venv/bin/activate
     pip install -r requirements.txt
     ```

### Syncing Between Platforms

The `.env` file and source code are platform-agnostic. To sync:

1. **Use Git** (recommended)
   ```bash
   git add .
   git commit -m "Update code"
   git push
   ```

2. **Or use cloud sync** (Dropbox, iCloud, OneDrive)
   - Just ensure `.env` is synced
   - `venv/` folder is platform-specific (don't sync)

## Docker Benefits

✅ **Identical environment** on both platforms  
✅ **No Python version conflicts**  
✅ **Isolated dependencies**  
✅ **Easy cleanup** (`docker-compose down`)  
✅ **Live code reload** (source mounted as volume)

## Troubleshooting

### macOS: Permission Denied

```bash
chmod +x run_monitor.sh check_pnl.sh dev.sh
```

### Docker: Port Already in Use

```bash
docker-compose down
# Then start again
docker-compose up -d
```

### Docker: Build Failed

```bash
# Clean rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## File Structure

```
Bybit_notion-main/
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Service orchestration
├── .dockerignore          # Docker build exclusions
├── .env                   # Environment variables (both platforms)
├── requirements.txt       # Python dependencies
│
├── run_monitor.bat        # Windows launcher
├── check_pnl.bat          # Windows PnL report
│
├── run_monitor.sh         # macOS/Linux launcher
├── check_pnl.sh           # macOS/Linux PnL report
├── dev.sh                 # Development helper
│
└── src/                   # Source code (platform-agnostic)
```

## Best Practices

1. **Always use `.env`** for configuration (never hardcode)
2. **Commit code changes** to Git regularly
3. **Don't commit** `.env` file (use `.env.example` as template)
4. **Use Docker** for production-like testing
5. **Use native Python** for faster iteration during development
