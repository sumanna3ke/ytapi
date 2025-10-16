# app.py
import os
import shutil
import tempfile
from flask import Flask, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
COOKIES_FILE = "cookies.txt"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def cleanup_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)

def auth_required_error(err: str) -> bool:
    if not err:
        return False
    err_lower = err.lower()
    return "sign in to confirm" in err_lower or "not a bot" in err_lower or "cookies" in err_lower

@app.route("/upload-cookies", methods=["POST"])
def upload_cookies():
    if 'file' not in request.files:
        return jsonify({"error": "Missing file (send as form-data with key 'file')"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    f.save(COOKIES_FILE)
    try:
        os.chmod(COOKIES_FILE, 0o600)
    except Exception:
        pass
    return jsonify({"status": "cookies_uploaded"}), 201

@app.route("/download", methods=["GET"])
def download_video():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    use_cookies = request.args.get("use_cookies", "0") in ("1", "true", "yes")

    tmp_dir = tempfile.mkdtemp(prefix="yt_dl_")
    outtmpl = os.path.join(tmp_dir, "%(title).100B.%(ext)s")

    ydl_opts = {
        "format": "best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "restrictfilenames": True,
        "merge_output_format": "mp4",
        "http_headers": {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/116.0.0.0 Safari/537.36"),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/"
        },
        "geo_bypass": True,
    }

    if use_cookies and os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        response = send_file(filename, as_attachment=True)
        cleanup_dir(tmp_dir)
        return response

    except Exception as e:
        cleanup_dir(tmp_dir)
        err_str = str(e)
        if auth_required_error(err_str):
            return jsonify({
                "error": "youtube_requires_auth",
                "message": "YouTube blocked this video. It may require login/age verification.",
                "fix": "Upload a fresh cookies.txt (Netscape format) via /upload-cookies and call /download?use_cookies=1",
                "detail": err_str
            }), 403
        return jsonify({"error": "download_failed", "detail": err_str}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
