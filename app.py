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


def select_best_format(formats):
    candidates = []

    for f in formats:
        if f.get("ext") != "mp4":
            continue
        if f.get("vcodec") == "none":
            continue
        if f.get("watermark") is False:
            candidates.append(f)

    if not candidates:
        for f in formats:
            if f.get("ext") == "mp4" and f.get("vcodec") != "none":
                candidates.append(f)

    if not candidates:
        return None

    return max(candidates, key=lambda f: f.get("height") or 0)


# -----------------------------
# Metadata endpoint (OPTIONNEL)
# -----------------------------
@app.route("/tiktok/info", methods=["POST"])
def tiktok_info():
    import yt_dlp

    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing url"}), 400

    url = data["url"]
    if not is_valid_tiktok_url(url):
        return jsonify({"error": "Invalid TikTok URL"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
            "Mobile/15E148 Safari/604.1"
        ),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        selected = select_best_format(formats)

        if not selected:
            return jsonify({"error": "No playable format"}), 404

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "resolution": f'{selected.get("width")}x{selected.get("height")}',
            "watermark": selected.get("watermark", True),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# PASS-THROUGH VIDEO STREAM
# -----------------------------
@app.route("/tiktok/stream", methods=["POST"])
def tiktok_stream():
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
            "-f", "bv*+ba/b",
            "-o", "-",
            "--merge-output-format", "mp4",
            "--no-part",
            "--quiet",
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
            "Content-Disposition": "attachment; filename=tiktok.mp4",
            "Cache-Control": "no-store",
            "Accept-Ranges": "none",
        },
    )


# -----------------------------
# Healthcheck
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







