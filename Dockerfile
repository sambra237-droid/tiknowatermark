FROM python:3.11-slim

# =========================
# Dépendances système
# =========================
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ca-certificates \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# =========================
# Installer curl-impersonate (ROBUSTE)
# =========================
RUN wget -O /tmp/curl-impersonate.tar.gz \
      https://github.com/lwthiker/curl-impersonate/releases/download/v0.6.1/curl-impersonate-v0.6.1.x86_64-linux-gnu.tar.gz \
 && tar -xzf /tmp/curl-impersonate.tar.gz -C /tmp \
 && find /tmp -type f -name "curl-impersonate-chrome*" -exec cp {} /usr/local/bin/curl-impersonate-chrome \; \
 && chmod +x /usr/local/bin/curl-impersonate-chrome \
 && rm -rf /tmp/curl-impersonate*

# =========================
# Variables yt-dlp
# =========================
ENV YTDLP_CURL="curl-impersonate-chrome"
ENV YTDLP_NO_UPDATE=1

# =========================
# App
# =========================
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8080

CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8080", "app:app"]







