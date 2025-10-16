from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict, Any


class ResolveRequest(BaseModel):
    url: HttpUrl = Field(..., description="Public TeraBox share URL")
    cookie: Optional[str] = Field(
        default=None,
        description="Optional Cookie header string for authenticated/private links",
    )
    user_agent: Optional[str] = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        ),
        description="User-Agent header to use during resolution",
    )
    timeout_seconds: int = Field(25, ge=5, le=120, description="Resolve timeout")
    use_browser: bool = Field(
        default=True,
        description="Allow headless browser fallback via Playwright if needed",
    )


class ResolvedFile(BaseModel):
    direct_url: HttpUrl
    filename: Optional[str] = None
    content_length: Optional[int] = None
    content_type: Optional[str] = None
    headers: Dict[str, Any] = {}


class ErrorResponse(BaseModel):
    detail: str
    info: Optional[Dict[str, Any]] = None
