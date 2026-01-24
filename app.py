from flask import Flask, request, jsonify, Response, stream_with_context
import subprocess
import tempfile
import os
import sys
import re
import shutil

app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "Roboto-Regular.ttf")
LOGO_PATH = os.path.join(ASSETS_DIR, "tiktok_logo.png")

CHUNK_SIZE = 8192  # streaming safe

# -----------------------------
# UTILS
# -----------------------------
def is_valid_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(vm\.tiktok\.com|tiktok\.com)", url))


def extract_username(url: str) -> str:
    """Extraction légère, jamais bloquante"""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "skip_download": True,
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("uploader") or "tiktok"
    except Exception:
        return "tiktok"


# -----------------------------
# VIDEO STREAM + WATERMARK
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

    temp_dir = tempfile.mkdtemp(prefix="tiktok_video_")
    input_video = os.path.join(temp_dir, "input.mp4")
    output_video = os.path.join(temp_dir, "output.mp4")

    try:
        # -----------------------------
        # 1️⃣ DOWNLOAD VIDEO (LOW RAM)
        # -----------------------------
        download_cmd = [
            sys.executable,
            "-m", "yt_dlp",
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "--no-part",
            "--no-playlist",
            "--quiet",
            "-o", input_video,
            url,
        ]

        subprocess.run(
            download_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )

        if not os.path.exists(input_video) or os.path.getsize(input_video) < 1024:
            return jsonify({"error": "Downloaded video is empty"}), 500

        # -----------------------------
        # 2️⃣ WATERMARK (ANTI-OOM)
        # -----------------------------
        filter_complex = (
            # ↓↓↓ réduction résolution = RAM ÷ 2-3
            "[0:v]scale=540:-2[v0];"
            "[1:v]scale=40:-1[logo];"
            "[v0][logo]overlay="
            "x='20 + (W-w-40)*between(mod(t,6),2,4)':"
            "y='20 + (H-h-40)*between(mod(t,6),3,6)',"
            f"drawtext=fontfile={FONT_PATH}:"
            f"text='@{username}':"
            "fontcolor=white@0.45:"
            "fontsize=22:"
            "shadowcolor=black@0.6:"
            "shadowx=2:shadowy=2:"
            "x='70 + (W-tw-140)*between(mod(t,6),2,4)':"
            "y='25 + (H-th-50)*between(mod(t,6),3,6)'"
        )

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-threads", "1",              # 🔥 CRITIQUE (anti-OOM)
            "-i", input_video,
            "-i", LOGO_PATH,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-preset", "ultrafast",       # 🔥 RAM minimale
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "copy",
            output_video,
        ]

        subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )

        if not os.path.exists(output_video) or os.path.getsize(output_video) < 1024:
            return jsonify({"error": "Watermark encoding failed"}), 500

        # -----------------------------
        # 3️⃣ STREAMING SAFE (Gunicorn)
        # -----------------------------
        def generate():
            with open(output_video, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
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

    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "Video processing failed",
            "details": e.stderr.decode(errors="ignore"),
        }), 500

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# -----------------------------
# HEALTHCHECK
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# -----------------------------
# LOCAL RUN
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)































