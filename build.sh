#!/usr/bin/env bash
# Render build script for TeraBox Downloader API

set -o errexit  # Exit on error

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing Playwright browsers and system dependencies..."
# Install Chromium browser with system dependencies
python -m playwright install --with-deps chromium

echo "Build complete!"
