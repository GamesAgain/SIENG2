FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libimage-exiftool-perl binwalk mediainfo pngcheck \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir hachoir==3.3.0 Pillow

WORKDIR /app
COPY src /app/src
ENTRYPOINT ["python", "-m", "src.core.analyzer.inspection.cli"]
