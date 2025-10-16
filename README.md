# TeraBox Downloader API

A small FastAPI service to resolve TeraBox share links into direct download URLs and optionally proxy the download stream. It uses lightweight HTML parsing first and falls back to a headless browser (Playwright) to intercept the generated download URL when needed.

## Features

- 🌐 **Beautiful Web Interface** - User-friendly website to generate download links
- 🔗 Resolve TeraBox share page to a direct file URL: `POST /resolve`
- ⬇️ Proxy-download endpoint with resume support: `GET /download?url=...`
- 🔐 Optional Cookie header for private/authenticated links
- 🎨 Modern, responsive design with dark theme
- 📱 Mobile-friendly interface
- 🚀 Fast API with full OpenAPI documentation
- 📊 CORS enabled by default (adjust in production)
- 📝 Logging via Loguru

## Tech stack

- FastAPI, Uvicorn
- httpx for HTTP
- BeautifulSoup4 for HTML parsing
- Playwright (Chromium) as a fallback

## Project structure

```
app/
  main.py
  models.py
  resolver.py
  logger.py
  __init__.py
static/
  index.html
  style.css
  script.js
requirements.txt
runtime.txt
render.yaml
build.sh
```

## Setup

1) Create and activate a virtual environment (recommended)

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Install Playwright browsers (for fallback)

```bash
python -m playwright install chromium
```

If step (3) fails, you can still use `/resolve` without the browser fallback by setting `use_browser=false` in your request.

## Run the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs for Swagger UI.

## Web Interface

Access the beautiful web interface at: **http://localhost:8000**

### How to Use:

1. **Open the website** in your browser
2. **Paste your TeraBox share URL** in the input field
3. **Click "Get Download Link"** and wait 10-30 seconds
4. **Download directly** or copy the link for later

### Features:
- ✨ Beautiful, modern dark theme UI
- 📊 Shows file information (name, size, type)
- 📋 One-click copy to clipboard
- 📱 Fully responsive for mobile devices
- ⚡ Real-time progress feedback
- 🎯 Supports all TeraBox domains

## API

### POST /resolve

Body:

```json
{
  "url": "https://teraboxapp.com/s/xxxxxxxx",
  "cookie": null,
  "user_agent": "Mozilla/5.0 ...",
  "timeout_seconds": 25,
  "use_browser": true
}
```

Response:

```json
{
  "direct_url": "https://...",
  "filename": "example.mp4",
  "content_length": 123456789,
  "content_type": "video/mp4",
  "headers": { "content-length": "123456789", "accept-ranges": "bytes" }
}
```

### GET /download

Query params:

- `url` (required): Direct file URL to proxy
- `filename` (optional): Override filename in Content-Disposition
- `cookie` (optional): Upstream Cookie header
- `user_agent` (optional): Upstream User-Agent header

This endpoint streams the file from the upstream URL to the client. It forwards `Range` headers to support resuming.

## Deploy on Render

### Option 1: Deploy with render.yaml (Recommended)

1. **Push your code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

2. **Connect to Render**
   - Go to [render.com](https://render.com) and sign up/login
   - Click "New +" → "Blueprint"
   - Connect your GitHub repository
   - Render will automatically detect `render.yaml` and configure the service
   - Click "Apply" to deploy

3. **Wait for deployment**
   - The build script will install Playwright and dependencies (takes ~5-10 minutes first time)
   - Once deployed, your API will be live at `https://your-service-name.onrender.com`

### Option 2: Manual Deployment

1. **Create a New Web Service**
   - Go to Render Dashboard → "New +" → "Web Service"
   - Connect your GitHub repository

2. **Configure the service**
   - **Name**: `terabox-downloader-api` (or your choice)
   - **Runtime**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free (or higher for production)

3. **Environment Variables** (optional)
   - `PLAYWRIGHT_BROWSERS_PATH`: `/opt/render/.cache/ms-playwright`

4. **Create Web Service** and wait for deployment

### Important Notes for Render

- **Python version**: The project uses Python 3.11 (specified in `runtime.txt`). Python 3.13+ has compatibility issues with some dependencies
- **Free tier limitations**: Free instances spin down after 15 minutes of inactivity and may take 30-60 seconds to wake up
- **Playwright on Free tier**: Works but builds take longer. Consider upgrading to Starter plan for faster builds
- **Health checks**: The `/health` endpoint is configured for Render health checks
- **Logs**: View deployment logs in Render Dashboard to troubleshoot issues

### Test your deployed API

```bash
# Health check
curl https://your-service-name.onrender.com/health

# Resolve a TeraBox link
curl -X POST https://your-service-name.onrender.com/resolve \
  -H "Content-Type: application/json" \
  -d '{"url":"https://teraboxapp.com/s/YOUR_SHARE_ID","use_browser":true}'
```

### Swagger UI

Access interactive API docs at: `https://your-service-name.onrender.com/docs`

## Notes and caveats

- TeraBox may change their frontend which could break static parsing. In that case, keep `use_browser=true` to allow Playwright fallback.
- For private links, provide a valid `cookie` string (from your logged-in session) in `POST /resolve` or `GET /download`.
- Be mindful of TeraBox Terms of Service and local laws. This project is for educational purposes.
