import asyncio
import json
import re
from typing import Optional, Dict, Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from .models import ResolveRequest, ResolvedFile


INITIAL_STATE_RE = re.compile(r"__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL)
DLINK_RE = re.compile(r"\b(dlink|download|get_file)\b", re.IGNORECASE)
URL_IN_QUOTES_RE = re.compile(r"https?://[^'\"\s>]+")


async def _head(client: httpx.AsyncClient, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    try:
        r = await client.head(url, headers=headers, follow_redirects=True, timeout=20)
        r.raise_for_status()
        info = {
            "content_length": int(r.headers.get("content-length")) if r.headers.get("content-length") else None,
            "content_type": r.headers.get("content-type"),
            "filename": _filename_from_headers(r.headers),
            "headers": dict(r.headers),
        }
        return info
    except Exception as e:
        logger.warning(f"HEAD failed for {url}: {e}")
        return {"headers": {}}


def _filename_from_headers(headers: httpx.Headers) -> Optional[str]:
    cd = headers.get("content-disposition")
    if not cd:
        return None
    match = re.search(r"filename\*=UTF-8''([^;]+)", cd)
    if match:
        try:
            from urllib.parse import unquote

            return unquote(match.group(1))
        except Exception:
            pass
    match = re.search(r'filename\s*=\s*"?([^";]+)"?', cd)
    if match:
        return match.group(1)
    return None


async def _try_parse_html(req: ResolveRequest) -> Optional[str]:
    headers = {"User-Agent": req.user_agent}
    if req.cookie:
        headers["Cookie"] = req.cookie

    async with httpx.AsyncClient(follow_redirects=True, timeout=req.timeout_seconds) as client:
        logger.info("Fetching TeraBox page for HTML parsing")
        resp = await client.get(str(req.url), headers=headers)
        resp.raise_for_status()

        html = resp.text

        # Try __INITIAL_STATE__ JSON extraction first
        m = INITIAL_STATE_RE.search(html)
        if m:
            try:
                state = json.loads(m.group(1))
                # heuristic: search for any URL fields that look like direct links
                text = json.dumps(state)
                urls = URL_IN_QUOTES_RE.findall(text)
                for u in urls:
                    if DLINK_RE.search(u):
                        logger.info("Found candidate direct URL in __INITIAL_STATE__")
                        return u
            except Exception as e:
                logger.debug(f"Failed to parse __INITIAL_STATE__: {e}")

        # Fallback: scan scripts and anchors
        soup = BeautifulSoup(html, "html.parser")
        # anchors
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if href and href.startswith("http") and DLINK_RE.search(href):
                return href
        # script bodies
        for script in soup.find_all("script"):
            content = script.string or script.text or ""
            if not content:
                continue
            for u in URL_IN_QUOTES_RE.findall(content):
                if DLINK_RE.search(u):
                    return u

    return None


async def _with_playwright(req: ResolveRequest) -> Optional[str]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        logger.warning(f"Playwright module not installed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Playwright not available: {e}")
        return None

    logger.info("Attempting Playwright headless resolution…")
    
    candidate_url: Optional[str] = None
    
    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
            except Exception as e:
                logger.error(f"Failed to launch Chromium browser (missing system dependencies?): {e}")
                return None
                
            context = await browser.new_context(
                user_agent=req.user_agent,
                extra_http_headers={"Cookie": req.cookie} if req.cookie else None,
            )

            def handle_response(response):
                nonlocal candidate_url
                try:
                    url = response.url
                    if DLINK_RE.search(url) or any(
                        k in url for k in [
                            "response.baidupcs.com",
                            "download",
                            "get_file",
                            "/file/download",
                            "d.terabox",
                            "download.terabox",
                        ]
                    ):
                        logger.info(f"Captured potential download URL: {url}")
                        candidate_url = url
                except Exception:
                    pass

            context.on("response", handle_response)
            page = await context.new_page()
            try:
                await page.goto(str(req.url), timeout=req.timeout_seconds * 1000, wait_until="domcontentloaded")
                # Click common buttons to trigger generation if present
                try:
                    dl_selectors = [
                        "text=Download",
                        "button:has-text('Download')",
                        "a:has-text('Download')",
                    ]
                    for sel in dl_selectors:
                        el = await page.query_selector(sel)
                        if el:
                            await el.click(timeout=3000)
                            await page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Wait a bit for network
                await page.wait_for_timeout(4000)
            finally:
                await context.close()
                await browser.close()
    except Exception as e:
        logger.error(f"Playwright execution error: {e}")
        return None

    return candidate_url


async def resolve_terabox(req: ResolveRequest) -> ResolvedFile:
    # 1) Try to parse HTML
    url = await _try_parse_html(req)

    # 2) Fallback to Playwright if allowed and needed
    if not url and req.use_browser:
        url = await _with_playwright(req)

    if not url:
        raise ValueError("Could not resolve a direct download URL. The link may be private or TeraBox changed its layout.")

    # 3) Probe metadata via HEAD
    headers = {"User-Agent": req.user_agent}
    if req.cookie:
        headers["Cookie"] = req.cookie
    async with httpx.AsyncClient(follow_redirects=True, timeout=req.timeout_seconds) as client:
        meta = await _head(client, url, headers)

    return ResolvedFile(
        direct_url=url,
        filename=meta.get("filename"),
        content_length=meta.get("content_length"),
        content_type=meta.get("content_type"),
        headers=meta.get("headers", {}),
    )
