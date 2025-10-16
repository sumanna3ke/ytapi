import asyncio
import json
import re
from typing import Optional, Dict, Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from .models import ResolveRequest, ResolvedFile


# Updated patterns for modern TeraBox
INITIAL_STATE_RE = re.compile(r"window\.data\s*=\s*(\{.*?\})\s*;?\s*</script>", re.DOTALL)
JSON_STATE_RE = re.compile(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', re.DOTALL)
DLINK_RE = re.compile(r"\b(dlink|download|get_file|d\.terabox|file\.baidu\.com|baidupcs\.com|terabox\.com/s/)\b", re.IGNORECASE)
URL_IN_QUOTES_RE = re.compile(r'["\'](https?://[^"\'\s]+)["\']')
FILENAME_RE = re.compile(r'filename[^;=\n]*=(([\'"])?([^;\n]*?)(?(2)\2|))', re.IGNORECASE)


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
    headers = {
        "User-Agent": req.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.terabox.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "max-age=0"
    }
    
    if req.cookie:
        headers["Cookie"] = req.cookie

    async with httpx.AsyncClient(
        follow_redirects=True, 
        timeout=req.timeout_seconds,
        http2=True
    ) as client:
        try:
            logger.info(f"Fetching TeraBox page: {req.url}")
            resp = await client.get(str(req.url), headers=headers)
            resp.raise_for_status()
            html = resp.text

            # Try to find direct download URL in various patterns
            patterns = [
                # Try to find direct URLs in the page
                (r'(https?://[^\s"\']+?/file/[^\s"\']+)', 'Direct file pattern'),
                (r'(https?://[^\s"\']+?/share/link[^\s"\']+)', 'Share link pattern'),
                (r'"dlink"\s*:\s*"([^"]+)"', 'DLink in JSON'),
                (r'downloadUrl\s*[=:]\s*["\']([^"\']+)["\']', 'downloadUrl in JS'),
            ]

            for pattern, desc in patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for url in matches:
                    url = url if isinstance(url, str) else url[0] if isinstance(url, tuple) else str(url)
                    if any(x in url.lower() for x in ['download', 'd.terabox', 'baidupcs', 'terabox.com/s/']):
                        logger.info(f"Found URL with {desc}: {url}")
                        return url

            # Try JSON data in script tags
            for script in re.findall(r'<script[^>]*>([\s\S]*?)</script>', html):
                if not script.strip():
                    continue
                
                # Look for direct URLs in script content
                urls = re.findall(r'["\'](https?://[^"\'\s]+)["\']', script)
                for url in urls:
                    if any(x in url.lower() for x in ['download', 'd.terabox', 'baidupcs', 'terabox.com/s/']):
                        logger.info(f"Found URL in script: {url}")
                        return url
                
                # Try to parse as JSON
                try:
                    data = json.loads(script)
                    # Flatten nested JSON and search for URLs
                    flat = {}
                    def flatten_json(nested_json, prefix=''):
                        if isinstance(nested_json, dict):
                            for k, v in nested_json.items():
                                flatten_json(v, f"{prefix}{k}.")
                        elif isinstance(nested_json, list):
                            for i, v in enumerate(nested_json):
                                flatten_json(v, f"{prefix}{i}.")
                        else:
                            flat[prefix[:-1]] = nested_json
                    
                    flatten_json(data)
                    for k, v in flat.items():
                        if not isinstance(v, str):
                            continue
                        if 'url' in k.lower() and 'http' in v and any(x in v.lower() for x in ['download', 'd.terabox', 'baidupcs']):
                            logger.info(f"Found URL in JSON data at {k}: {v}")
                            return v
                except (json.JSONDecodeError, TypeError):
                    continue

            # Fallback: Look for iframe or embed sources
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup.find_all(['iframe', 'embed', 'source', 'a']):
                url = tag.get('src') or tag.get('href')
                if not url or not isinstance(url, str):
                    continue
                if url.startswith('http') and any(x in url.lower() for x in ['download', 'd.terabox', 'baidupcs']):
                    logger.info(f"Found URL in {tag.name} tag: {url}")
                    return url

        except Exception as e:
            logger.warning(f"Error parsing HTML: {str(e)}")

    return None


async def _with_playwright(req: ResolveRequest) -> Optional[str]:
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError as e:
        logger.warning(f"Playwright module not installed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Playwright not available: {e}")
        return None

    logger.info("Attempting Playwright headless resolution...")
    
    candidate_url: Optional[str] = None
    
    try:
        async with async_playwright() as p:
            # Try with Chromium first, fall back to Firefox if needed
            browser = None
            for browser_type in [p.chromium, p.firefox]:
                try:
                    browser = await browser_type.launch(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox']
                    )
                    break
                except Exception as e:
                    logger.warning(f"Failed to launch {browser_type.name}: {e}")
                    continue
            
            if not browser:
                logger.error("Failed to launch any browser")
                return None
                
            try:
                context = await browser.new_context(
                    user_agent=req.user_agent,
                    viewport={'width': 1920, 'height': 1080},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Referer": "https://www.terabox.com/",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        **({"Cookie": req.cookie} if req.cookie else {})
                    },
                    # Enable JavaScript and other browser features
                    java_script_enabled=True,
                    bypass_csp=True,
                    ignore_https_errors=True,
                )

                # Intercept network requests to find download URLs
                async def handle_route(route, request):
                    url = request.url.lower()
                    if any(x in url for x in ['d.terabox', 'baidupcs', 'download', 'get_file']):
                        nonlocal candidate_url
                        candidate_url = request.url
                        logger.info(f"Intercepted potential download URL: {request.url}")
                    await route.continue_()

                # Create a new page
                page = await context.new_page()
                await page.route('**/*', handle_route)

                # Navigate to the URL
                logger.info(f"Navigating to: {req.url}")
                try:
                    await page.goto(
                        str(req.url),
                        timeout=req.timeout_seconds * 1000,
                        wait_until="domcontentloaded"
                    )
                except PlaywrightTimeoutError:
                    logger.warning("Page load timed out, continuing with current state")

                # Common download button selectors
                download_selectors = [
                    "button:has-text('Download')",
                    "a:has-text('Download')",
                    "button:has-text('Download Now')",
                    "a:has-text('Download Now')",
                    "button:contains('下载')",  # Chinese for Download
                    "a:contains('下载')",
                    "button.download-btn",
                    "a.download-btn",
                    "button[data-action='download']",
                    "a[data-action='download']",
                    "button[onclick*='download']",
                    "a[onclick*='download']",
                ]

                # Try to find and click download buttons
                for selector in download_selectors:
                    try:
                        logger.info(f"Trying selector: {selector}")
                        await page.wait_for_selector(selector, timeout=5000)
                        element = await page.query_selector(selector)
                        if element:
                            logger.info(f"Clicking element: {selector}")
                            await element.click()
                            await page.wait_for_timeout(3000)  # Wait for any network requests
                            if candidate_url:  # If we found a URL, we're done
                                break
                    except Exception as e:
                        logger.debug(f"Selector {selector} failed: {e}")
                        continue

                # If we still don't have a URL, try to extract from page content
                if not candidate_url:
                    content = await page.content()
                    urls = re.findall(r'["\'](https?://[^"\'\s]+)["\']', content)
                    for url in urls:
                        if any(x in url.lower() for x in ['d.terabox', 'baidupcs', 'download', 'get_file']):
                            candidate_url = url
                            logger.info(f"Found URL in page content: {url}")
                            break

                # Wait for any pending network requests
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except:
                    pass

            finally:
                await context.close()
                await browser.close()

    except Exception as e:
        logger.error(f"Playwright error: {str(e)}")
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
