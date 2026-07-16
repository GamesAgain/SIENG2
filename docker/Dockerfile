# SIENG2 analyzer backend — packages binwalk/exiftool (Linux-only CLI tools the
# analyzer depends on) so the Windows GUI can run steganalysis via `docker run`
# instead of requiring these tools installed natively. See docker_bridge.py.
FROM python:3.12-slim-bookworm

# binwalk / libimage-exiftool-perl: the two external CLI tools analyzer/external_tools/*
# shells out to. libgl1 / libglib2.0-0: shared libs opencv-python (used by avi_handler.py) needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    binwalk \
    libimage-exiftool-perl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY docker/requirements-analyzer.txt .
RUN pip install --no-cache-dir -r requirements-analyzer.txt

# Only the analyzer package is needed inside the container (self-contained,
# no imports from src.core.stego/src.core.crypto/etc.)
COPY src/__init__.py src/__init__.py
COPY src/core/__init__.py src/core/__init__.py
COPY src/core/analyzer/ src/core/analyzer/

ENTRYPOINT ["python", "-m", "src.core.analyzer.cli"]
