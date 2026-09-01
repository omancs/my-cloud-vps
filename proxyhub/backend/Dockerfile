FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Mihomo (Clash Meta) official core
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then MIHOMO_FILE="mihomo-linux-amd64-compatible-v1.19.29.gz"; \
    elif [ "$ARCH" = "arm64" ]; then MIHOMO_FILE="mihomo-linux-arm64-v1.19.29.gz"; \
    else MIHOMO_FILE="mihomo-linux-amd64-compatible-v1.19.29.gz"; fi && \
    wget -q "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.29/${MIHOMO_FILE}" -O /tmp/mihomo.gz && \
    gzip -d /tmp/mihomo.gz && \
    mv /tmp/mihomo* /usr/local/bin/mihomo && \
    chmod +x /usr/local/bin/mihomo

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
