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
        # 1️⃣ DOWNLOAD VIDEO
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
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"error": "Downloaded video is empty"}), 500

        # -----------------------------
        # 2️⃣ WATERMARK TikTok-LIKE (PRO)
        # -----------------------------
        filter_complex = (
            "[0:v]scale=540:-2[v];"
            "[v]"
            "drawtext=fontfile={font}:"
            "text='TikTok':"
            "fontcolor=white@0.35:"
            "fontsize=h*0.038:"
            "shadowcolor=black@0.5:"
            "shadowx=1:shadowy=1:"
            "x='if(between(mod(t,8),0,4),"
            "40+sin(t*6)*2,"
            "W-tw-40+sin(t*6)*2)':"
            "y='H-th-60':"
            "alpha='if(between(mod(t,8),0,3.6),1,0)':"
            "[v1];"
            "[v1]"
            "drawtext=fontfile={font}:"
            "text='@{user}':"
            "fontcolor=white@0.30:"
            "fontsize=h*0.032:"
            "shadowcolor=black@0.4:"
            "shadowx=1:shadowy=1:"
            "x='if(between(mod(t,8),0,4),"
            "40+sin(t*6)*2,"
            "W-tw-40+sin(t*6)*2)':"
            "y='H-th-32':"
            "alpha='if(between(mod(t,8),0,3.6),1,0)'"
        ).format(
            font=FONT_PATH.replace("\\", "\\\\"),
            user=username.replace("'", "")
        )

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-threads", "1",
            "-i", input_video,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-preset", "ultrafast",
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
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"error": "Watermark encoding failed"}), 500

        # -----------------------------
        # 3️⃣ STREAMING + CLEANUP SAFE
        # -----------------------------
        def generate():
            try:
                with open(output_video, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

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
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({
            "error": "Video processing failed",
            "details": e.stderr.decode(errors="ignore"),
        }), 500


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



































