from flask import Flask, request, jsonify, Response, stream_with_context
import re
import subprocess
import sys
import os

app = Flask(__name__)

# -----------------------------
# Utils
# -----------------------------
def is_valid_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(vm\.tiktok\.com|tiktok\.com)", url))


# -----------------------------
# PASS-THROUGH VIDEO STREAM (WITH WATERMARK, HD)
# -----------------------------
@app.route("/tiktok/stream/watermark", methods=["POST"])
def tiktok_stream_watermark():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing url"}), 400

    url = data["url"]
    if not is_valid_tiktok_url(url):
        return jsonify({"error": "Invalid TikTok URL"}), 400

    def generate():
        cmd = [
            sys.executable,
            "-m", "yt_dlp",
            "-f", "mp4",              # ⬅️ FORMAT DIRECT (avec watermark)
            "-o", "-",                # ⬅️ stdout
            "--no-part",
            "--quiet",
            "--no-playlist",
            url,
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1024 * 1024,
        )

        try:
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                yield chunk
        finally:
            process.stdout.close()
            process.stderr.close()
            process.wait()

    return Response(
        stream_with_context(generate()),
        content_type="video/mp4",
        headers={
            "Content-Disposition": "attachment; filename=tiktok_watermark.mp4",
            "Cache-Control": "no-store",
            "Accept-Ranges": "none",
        },
    )


# -----------------------------
# Health
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)











