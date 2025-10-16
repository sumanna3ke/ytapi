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

echo "Installing Playwright browsers..."
export PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright

# Try to install system dependencies if we have permissions
if command -v apt-get &> /dev/null; then
    echo "Attempting to install Chromium system dependencies..."
    # Try with playwright's built-in installer first
    python -m playwright install-deps chromium 2>&1 || {
        echo "Note: Could not install system dependencies (no sudo access)."
        echo "Chromium may still work with Render's base image libraries."
    }
fi

# Install Chromium browser
echo "Downloading Chromium browser..."
python -m playwright install chromium

echo "Verifying Playwright installation..."
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright installed successfully')"

echo "Build complete!"
