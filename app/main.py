from typing import Optional
from pathlib import Path

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Header, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .models import ResolveRequest, ResolvedFile, ErrorResponse
from .resolver import resolve_terabox
from .logger import logger

app = FastAPI(title="TeraBox Downloader API", version="0.1.0")

# Mount static files directory
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Enable permissive CORS by default; adjust for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def homepage():
    """Serve the web interface"""
    index_path = Path(__file__).parent.parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "TeraBox Downloader API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/resolve", response_model=ResolvedFile, responses={400: {"model": ErrorResponse}})
async def resolve_endpoint(payload: ResolveRequest):
    try:
        result = await resolve_terabox(payload)
        return result
    except ValueError as ve:
        logger.warning(f"Resolve error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Unexpected resolve error")
        raise HTTPException(status_code=500, detail="Failed to resolve link")


@app.get(
    "/download",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def download_endpoint(
    request: Request,
    url: str = Query(..., description="Direct file URL to proxy"),
    filename: Optional[str] = Query(None, description="Optional filename for Content-Disposition"),
    cookie: Optional[str] = Query(None, description="Optional Cookie header for upstream"),
    user_agent: Optional[str] = Query(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        description="User-Agent to use upstream",
    ),
):
    # Forward Range header if present to support resume
    range_header = request.headers.get("range")

    headers = {"User-Agent": user_agent}
    if range_header:
        headers["Range"] = range_header
    if cookie:
        headers["Cookie"] = cookie

    try:
        client = httpx.AsyncClient(follow_redirects=True, timeout=60)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to initialize HTTP client")

    async def streamer():
        async with client as c:
            async with c.stream("GET", url, headers=headers) as resp:
                # Raise for status but allow 206 Partial Content as OK
                if resp.status_code >= 400:
                    text = await resp.aread()
                    raise HTTPException(status_code=resp.status_code, detail=text.decode(errors="ignore")[:500])
                async for chunk in resp.aiter_bytes():
                    yield chunk

    # We need to first make a HEAD/initial GET to fetch headers to set response headers properly
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as probe:
        try:
            r = await probe.get(url, headers=headers, timeout=60)
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail=f"Upstream responded {r.status_code}")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Failed to probe upstream URL")
            raise HTTPException(status_code=500, detail="Failed to contact upstream")

        content_type = r.headers.get("content-type", "application/octet-stream")
        content_length = r.headers.get("content-length")
        status_code = 206 if range_header and r.status_code == 206 else 200

        response = StreamingResponse(streamer(), media_type=content_type, status_code=status_code)

        if content_length and not range_header:
            response.headers["Content-Length"] = content_length
        # Forward Accept-Ranges and Content-Range if present
        if r.headers.get("accept-ranges"):
            response.headers["Accept-Ranges"] = r.headers["accept-ranges"]
        if r.headers.get("content-range"):
            response.headers["Content-Range"] = r.headers["content-range"]

        # Content-Disposition
        disp_name = filename
        if not disp_name:
            # Try to infer from upstream headers
            from .resolver import _filename_from_headers  # type: ignore

            disp_name = _filename_from_headers(r.headers)  # type: ignore
        if disp_name:
            response.headers["Content-Disposition"] = f"attachment; filename=\"{disp_name}\""

        return response


@app.exception_handler(httpx.HTTPError)
async def httpx_error_handler(request: Request, exc: httpx.HTTPError):
    logger.warning(f"HTTP error: {exc}")
    return JSONResponse(status_code=502, content={"detail": "Upstream HTTP error"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
