#!/usr/bin/env bash
# Render build script for TeraBox Downloader API

set -o errexit  # Exit on error

echo "Checking Python version..."
python --version

# Check if Python 3.13 is being used (incompatible with greenlet)
PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Detected Python version: $PYTHON_VERSION"

if [[ "$PYTHON_VERSION" == "3.13" ]]; then
    echo "ERROR: Python 3.13 detected, but it's incompatible with some dependencies."
    echo "Please ensure runtime.txt or .python-version specifies Python 3.11"
    echo "In Render Dashboard: Settings > Manual Deploy > Clear build cache & deploy"
    exit 1
fi

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing Playwright browsers and system dependencies..."
# Install Chromium browser with system dependencies
python -m playwright install --with-deps chromium

echo "Build complete!"
