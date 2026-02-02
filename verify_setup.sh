#!/bin/bash
# Setup verification script for cross-platform development

echo "=== Cross-Platform Setup Verification ==="
echo ""

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    echo "   ✅ Docker installed: $(docker --version)"
    
    if docker info &> /dev/null; then
        echo "   ✅ Docker daemon running"
    else
        echo "   ⚠️  Docker daemon not running"
    fi
else
    echo "   ❌ Docker not found"
fi

echo ""

# Check Docker Compose
echo "2. Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "   ✅ Docker Compose installed: $(docker-compose --version)"
else
    echo "   ❌ Docker Compose not found"
fi

echo ""

# Check Python
echo "3. Checking Python..."
if command -v python3 &> /dev/null; then
    echo "   ✅ Python installed: $(python3 --version)"
elif command -v python &> /dev/null; then
    echo "   ✅ Python installed: $(python --version)"
else
    echo "   ❌ Python not found"
fi

echo ""

# Check .env file
echo "4. Checking configuration..."
if [ -f ".env" ]; then
    echo "   ✅ .env file exists"
else
    echo "   ⚠️  .env file not found (copy from .env.example)"
fi

echo ""

# Check script permissions
echo "5. Checking script permissions..."
if [ -x "run_monitor.sh" ]; then
    echo "   ✅ run_monitor.sh is executable"
else
    echo "   ⚠️  run_monitor.sh not executable (run: chmod +x *.sh)"
fi

echo ""

# Summary
echo "=== Setup Summary ==="
echo "Files created:"
echo "  - Dockerfile"
echo "  - docker-compose.yml"
echo "  - .dockerignore"
echo "  - run_monitor.sh"
echo "  - check_pnl.sh"
echo "  - dev.sh"
echo "  - CROSS_PLATFORM.md"
echo ""
echo "Next steps:"
echo "  1. Ensure .env file is configured"
echo "  2. On macOS: chmod +x *.sh"
echo "  3. Test with: docker-compose up -d"
echo "  4. View logs: docker-compose logs -f"
