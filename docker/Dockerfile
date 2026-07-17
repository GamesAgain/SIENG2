# SIENG2 analyzer backend — packages binwalk/exiftool (Linux-only CLI tools the
# analyzer depends on) so the Windows GUI can run steganalysis via `docker run`
# instead of requiring these tools installed natively. See docker_bridge.py.
FROM python:3.12-slim-bookworm

# binwalk / libimage-exiftool-perl: external CLI tools analyzer/external_tools/* shells out to.
# libgl1 / libglib2.0-0: shared libs opencv-python (used by avi_handler.py) needs.
# ruby: runtime for the zsteg gem (installed below) - LSB extraction/enumeration for PNG & BMP.
# binutils: provides the GNU `strings` CLI (printable-text extraction from raw bytes).
RUN apt-get update && apt-get install -y --no-install-recommends \
    binwalk \
    libimage-exiftool-perl \
    libgl1 \
    libglib2.0-0 \
    ruby \
    file \
    binutils \
    p7zip-full \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# zsteg: de-facto tool for detecting/extracting LSB steganography in PNG/BMP
# (pure-Ruby deps, no build toolchain needed).
RUN gem install zsteg --no-document

WORKDIR /app

COPY docker/requirements-analyzer.txt .
RUN pip install --no-cache-dir -r requirements-analyzer.txt

# Only the analyzer package is needed inside the container (self-contained,
# no imports from src.core.stego/src.core.crypto/etc.)
COPY src/__init__.py src/__init__.py
COPY src/core/__init__.py src/core/__init__.py
COPY src/core/analyzer/ src/core/analyzer/

ENTRYPOINT ["python", "-m", "src.core.analyzer.cli"]
