from flask import Flask, request, Response, jsonify, send_file
import subprocess
import os
import re
import uuid
import yt_dlp

# --------------------------------------------------
# App
# --------------------------------------------------
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
TMP_DIR = os.path.join(BASE_DIR, "tmp")

FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "Roboto-Regular.ttf")
LOGO_PATH = os.path.join(ASSETS_DIR, "tiktok_logo.png")

os.makedirs(TMP_DIR, exist_ok=True)

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

# --------------------------------------------------
# Utils
# --------------------------------------------------
def is_valid_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(vm\.tiktok\.com|tiktok\.com)", url))


def extract_username(url: str) -> str:
    try:
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "skip_download": True,
            "user_agent": MOBILE_UA,
        }) as ydl:
            info = ydl.extract_info(url, download=False)
        return info.get("uploader") or "tiktok"
    except Exception:
        return "tiktok"


def safe_remove(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

# --------------------------------------------------
# Route principale
# --------------------------------------------------
@app.route("/tiktok/download", methods=["POST"])
def tiktok_download():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing url"}), 400

    url = data["url"]
    if not is_valid_tiktok_url(url):
        return jsonify({"error": "Invalid TikTok URL"}), 400

    username = extract_username(url)
    uid = uuid.uuid4().hex

    raw_path = os.path.join(TMP_DIR, f"raw_{uid}.mp4")
    final_path = os.path.join(TMP_DIR, f"final_{uid}.mp4")

    # --------------------------------------------------
    # 1️⃣ Télécharger la vidéo (SANS watermark)
    # --------------------------------------------------
    ydl_opts = {
        "outtmpl": raw_path,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "user_agent": MOBILE_UA,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        safe_remove(raw_path)
        return jsonify({"error": "Download failed"}), 500

    if not os.path.exists(raw_path) or os.path.getsize(raw_path) < 100_000:
        safe_remove(raw_path)
        return jsonify({"error": "Empty video (TikTok blocked)"}), 500

    # --------------------------------------------------
    # 2️⃣ Appliquer le watermark animé façon TikTok
    # --------------------------------------------------
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", raw_path,
        "-i", LOGO_PATH,
        "-filter_complex",
        (
            "[1:v]scale=120:-1[logo];"
            "[0:v][logo]overlay="
            "x='if(mod(t,6)<3,20,W-w-20)':"
            "y='if(mod(t,6)<3,20,H-h-20)',"
            "drawtext="
            f"fontfile={FONT_PATH}:"
            f"text='@{username}':"
            "fontsize=26:"
            "fontcolor=white@0.45:"
            "shadowcolor=black@0.5:"
            "shadowx=2:shadowy=2:"
            "x='if(mod(t,6)<3,20,W-tw-20)':"
            "y='if(mod(t,6)<3,150,H-th-150)'"
        ),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "copy",
        final_path,
    ]

    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    safe_remove(raw_path)

    if not os.path.exists(final_path):
        return jsonify({"error": "Watermark failed"}), 500

    # --------------------------------------------------
    # 3️⃣ Stream + cleanup
    # --------------------------------------------------
    def stream_and_cleanup():
        try:
            with open(final_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
        finally:
            safe_remove(final_path)

    return Response(
        stream_and_cleanup(),
        content_type="video/mp4",
        headers={
            "Content-Disposition": "attachment; filename=tiktok_watermarked.mp4",
            "Cache-Control": "no-store",
            "Accept-Ranges": "none",
        },
    )

# --------------------------------------------------
# Healthcheck
# --------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)













