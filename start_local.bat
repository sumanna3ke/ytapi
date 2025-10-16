@echo off
echo Starting TeraBox Downloader API locally...
echo.
echo The website will be available at: http://localhost:8000
echo API docs will be at: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
