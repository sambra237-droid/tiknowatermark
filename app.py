from flask import Flask, request, Response, stream_with_context, jsonify
import subprocess
import tempfile
import os
import sys
import re
import shutil

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "Roboto-Regular.ttf")
LOGO_PATH = os.path.join(BASE_DIR, "tiktok_logo.png")

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

def is_valid_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(vm\.tiktok\.com|tiktok\.com)", url))


def extract_username(url: str) -> str:
    import yt_dlp
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


@app.route("/tiktok/stream", methods=["POST"])
def tiktok_stream():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "Missing url"}), 400

    url = data["url"].strip()
    if not is_valid_tiktok_url(url):
        return jsonify({"error": "Invalid TikTok URL"}), 400

    username = extract_username(url)

    temp_dir = tempfile.mkdtemp(prefix="tiktok_video_")
    input_video = os.path.join(temp_dir, "input.mp4")
    output_video = os.path.join(temp_dir, "output.mp4")

    try:
        # 1️⃣ Téléchargement stable
        subprocess.run(
            [
                sys.executable,
                "-m", "yt_dlp",
                "-f", "bv*+ba/b",
                "--merge-output-format", "mp4",
                "--no-part",
                "--no-playlist",
                "--user-agent", MOBILE_UA,
                "-o", input_video,
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )

        if not os.path.exists(input_video) or os.path.getsize(input_video) < 1024:
            return jsonify({"error": "Downloaded video is empty"}), 500

        # 2️⃣ Watermark façon TikTok
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

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", input_video,
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                output_video,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )

        if not os.path.exists(output_video) or os.path.getsize(output_video) < 1024:
            return jsonify({"error": "Watermark rendering failed"}), 500

        # 3️⃣ Streaming depuis disque
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
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})















