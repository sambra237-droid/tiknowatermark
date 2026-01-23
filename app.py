from flask import Flask, request, Response, stream_with_context, jsonify
import subprocess
import tempfile
import os
import sys
import re
import shutil

app = Flask(__name__)

# -----------------------------
# Paths & config
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "Roboto-Regular.ttf")
LOGO_PATH = os.path.join(BASE_DIR, "tiktok_logo.png")

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

# -----------------------------
# Utils
# -----------------------------
def is_valid_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(vm\.tiktok\.com|tiktok\.com)", url))


def extract_username(url: str) -> str:
    """
    Extraction metadata légère (safe)
    """
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "skip_download": True,
            "user_agent": MOBILE_UA,
        }) as ydl:
            info = ydl.extract_info(url, download=False)
        return info.get("uploader") or info.get("channel") or "tiktok"
    except Exception:
        return "tiktok"


# -----------------------------
# STREAM VIDEO WITH WATERMARK
# -----------------------------
@app.route("/tiktok/stream", methods=["POST"])
def tiktok_stream():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "Missing url"}), 400

    url = data["url"].strip()
    if not is_valid_tiktok_url(url):
        return jsonify({"error": "Invalid TikTok URL"}), 400

    username = extract_username(url)

    # Dossier temporaire (/tmp sur Fly.io)
    temp_dir = tempfile.mkdtemp(prefix="tiktok_video_")
    input_video = os.path.join(temp_dir, "input.mp4")
    output_video = os.path.join(temp_dir, "output.mp4")

    try:
        # 1️⃣ Téléchargement STABLE (comme MP3)
        download_cmd = [
            sys.executable,
            "-m", "yt_dlp",
            "-f", "bestvideo+bestaudio/best",
            "--no-part",
            "--no-playlist",
            "--user-agent", MOBILE_UA,
            "-o", input_video,
            url,
        ]

        result = subprocess.run(
            download_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            return jsonify({
                "error": "TikTok blocked video download",
                "details": result.stderr.decode(errors="ignore"),
            }), 502

        if not os.path.exists(input_video) or os.path.getsize(input_video) < 1024:
            return jsonify({"error": "Downloaded video is empty"}), 500

        # 2️⃣ Watermark animé façon TikTok
        vf = (
            f"movie={LOGO_PATH}[logo];"
            "[in][logo]overlay="
            "x='if(mod(t,6)<3,20,W-w-20)':"
            "y='if(mod(t,6)<3,20,H-h-20)',"
            f"drawtext=fontfile={FONT_PATH}:"
            f"text='@{username}':"
            "fontcolor=white@0.5:"
            "fontsize=26:"
            "shadowcolor=black@0.6:"
            "shadowx=2:shadowy=2:"
            "x='if(mod(t,6)<3,20,W-tw-20)':"
            "y='if(mod(t,6)<3,60,H-th-60)'"
        )

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", input_video,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_video,
        ]

        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            return jsonify({
                "error": "Watermark rendering failed",
                "details": result.stderr.decode(errors="ignore"),
            }), 500

        if not os.path.exists(output_video) or os.path.getsize(output_video) < 1024:
            return jsonify({"error": "Final video is empty"}), 500

        # 3️⃣ Streaming depuis disque (safe Gunicorn / Fly.io)
        def generate():
            with open(output_video, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk

        return Response(
            stream_with_context(generate()),
            content_type="video/mp4",
            headers={
                "Content-Disposition": "attachment; filename=tiktok_watermarked.mp4",
                "Cache-Control": "no-store",
                "Accept-Ranges": "none",
            },
        )

    finally:
        # 4️⃣ Nettoyage garanti
        shutil.rmtree(temp_dir, ignore_errors=True)


# -----------------------------
# Healthcheck
# -----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# -----------------------------
# Run (local)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
















