from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pytube import YouTube
from typing import Optional
import os
import uuid

app = FastAPI(title="YouTube Downloader API",
             description="API for downloading YouTube videos and audio",
             version="1.0.0")

# CORS middleware to allow requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

@app.get("/")
async def read_root():
    return {"message": "Welcome to YouTube Downloader API. Use /docs for API documentation."}

@app.get("/video_info")
async def get_video_info(url: str = Query(..., description="YouTube video URL")):
    try:
        yt = YouTube(url)
        return {
            "title": yt.title,
            "author": yt.author,
            "length": yt.length,
            "views": yt.views,
            "thumbnail_url": yt.thumbnail_url,
            "streams": [
                {
                    "itag": stream.itag,
                    "mime_type": stream.mime_type,
                    "resolution": stream.resolution if hasattr(stream, 'resolution') else None,
                    "fps": stream.fps if hasattr(stream, 'fps') else None,
                    "type": "video" if "video" in stream.mime_type else "audio"
                }
                for stream in yt.streams
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download")
async def download_video(
    url: str = Query(..., description="YouTube video URL"),
    itag: Optional[int] = Query(None, description="Stream itag (optional)"),
    format: str = Query("mp4", description="Output format (mp4 or mp3)")
):
    try:
        yt = YouTube(url)
        
        if format.lower() == "mp3":
            # Get audio stream
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if not stream:
                raise HTTPException(status_code=400, detail="No audio stream found")
            
            # Download the audio
            temp_filename = f"downloads/{str(uuid.uuid4())}.mp3"
            stream.download(filename=temp_filename)
            
            return FileResponse(
                temp_filename,
                media_type="audio/mp3",
                filename=f"{yt.title}.mp3"
            )
        else:
            # Get video stream
            if itag:
                stream = yt.streams.get_by_itag(itag)
                if not stream:
                    raise HTTPException(status_code=400, detail=f"No stream found with itag: {itag}")
            else:
                # Default to highest resolution progressive stream
                stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                if not stream:
                    stream = yt.streams.get_highest_resolution()
            
            # Download the video
            temp_filename = f"downloads/{str(uuid.uuid4())}.mp4"
            stream.download(filename=temp_filename)
            
            return FileResponse(
                temp_filename,
                media_type="video/mp4",
                filename=f"{yt.title}.mp4"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
