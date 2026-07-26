# HE Manager backend API image. The Vue frontend is served by the separate
# nginx service, while this image serves Web and Android API traffic. Target
# arch: x86_64 / N100. Video thumbnails use cv2/OpenCV, not ffmpeg.
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install deps first so the layer caches across code changes.
COPY backend/requirements.txt ./requirements.txt
# The N100 host has no NVIDIA GPU. Installing torch from the general mirror
# pulled CUDA + Triton into the image (over 4 GB of unusable libraries), so
# install the official CPU wheel first; sentence-transformers then reuses it.
ARG TORCH_VERSION=2.9.1+cpu
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==${TORCH_VERSION}" \
    && pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r requirements.txt

# App package only — DB and media live on mounted volumes, never in the image.
COPY backend/app ./app

# Pre-create the mount targets so first boot works even before a bind exists.
# The app derives these from cwd=/srv: .thumbnails -> /srv/.thumbnails, and
# the external cover cache as abspath(cwd/../covers) -> /covers.
RUN mkdir -p /data /srv/.thumbnails /covers /srv/external_downloads

ENV HE_DATABASE_URL=sqlite:////data/library.db \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1

EXPOSE 8010

# --no-access-log mirrors he.ps1: keeps the ?token= query string out of logs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010", "--no-access-log"]
