#!/bin/bash
# Workspace setup script for tiktok_farm
# Run this script after cloning or in a fresh environment

set -e

REPO_URL="https://github.com/cda0345/tiktok_farm.git"

echo "🔧 Setting up tiktok_farm workspace..."

# Configure git remote origin if not already set
if ! git remote get-url origin &>/dev/null; then
    echo "➕ Adding git remote origin: $REPO_URL"
    git remote add origin "$REPO_URL"
else
    echo "✅ Git remote origin already configured: $(git remote get-url origin)"
fi

# Determine python executable
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo "❌ Python not found. Please install Python 3 and re-run this script."
    exit 1
fi

# Create Python virtual environment if not present
if [ ! -d ".venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    "$PYTHON" -m venv .venv
fi

# Activate virtual environment
# shellcheck disable=SC1091
source .venv/bin/activate

# Install dependencies
if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt not found. Cannot install dependencies."
    exit 1
fi
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo "   Activate the virtual environment with: source .venv/bin/activate"
