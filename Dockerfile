FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
LABEL org.opencontainers.image.title="TITAN OS"
LABEL org.opencontainers.image.description="Athletic Training Intelligence System"

RUN useradd -m -u 1000 titan
USER titan
WORKDIR /app

COPY --from=builder /root/.local /home/titan/.local
ENV PATH=/home/titan/.local/bin:$PATH

COPY --chown=titan:titan titan/ ./titan/
COPY --chown=titan:titan requirements.txt ./

ENV TITAN_DATA_DIR=/data
VOLUME /data

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python3 -c \
    "from titan.core.database import DatabaseManager; DatabaseManager('/data/titan.db')" \
    || exit 1

ENTRYPOINT ["python3", "-m", "titan"]
