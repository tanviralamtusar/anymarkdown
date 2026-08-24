FROM python:3.13-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV EXIFTOOL_PATH=/usr/bin/exiftool
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV PYTHONUNBUFFERED=1

# Runtime dependencies used by markitdown's audio/image converters
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    exiftool \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY packages /app/packages
RUN pip install --no-cache-dir "/app/packages/markitdown[all]"

COPY webui /app/webui
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    itsdangerous \
    python-docx \
    openai

# Default USERID and GROUPID, override at build time if needed
ARG USERID=nobody
ARG GROUPID=nogroup
USER $USERID:$GROUPID

WORKDIR /app/webui
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
