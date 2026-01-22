from flask import Flask, request, jsonify, Response, stream_with_context
import re
import subprocess
import os
import sys

app = Flask(__name__)

# -----------------------------
# Utils
# -----------------------------
def is_valid_tiktok_url(url: str) -> bool:
    return bool(re.search(r"(vm\.tiktok\.com|tiktok\.com)", url))


# -----------------------------
# VIDEO STREAM (AVEC WATERMARK – QUALITÉ MAX)
# -----------------------------
@app.route("/tiktok/video", methods=["POST"])
def tiktok_video_watermark_hd():
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
            # 🔑 QUALITÉ MAX (comme sans filigrane)
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", "-",
            "--no-part",
            "--quiet",
            "--user-agent",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
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
            "Content-Disposition": "attachment; filename=tiktok_watermark_hd.mp4",
            "Cache-Control": "no-store",
            "Accept-Ranges": "none",
        },
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)









