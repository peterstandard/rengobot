# Stage 1: Build Rust dependencies
FROM rust:1-slim-bookworm AS builder

RUN cargo install sgf-render resvg

# Stage 2: Python runtime
FROM python:3.12-slim-bookworm

# Install Noto Sans fonts and certificates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-core \
        ca-certificates \
        fontconfig && \
    rm -rf /var/lib/apt/lists/* && \
    fc-cache -fv

# Copy compiled Rust binaries from builder
COPY --from=builder /usr/local/cargo/bin/sgf-render /usr/local/bin/sgf-render
COPY --from=builder /usr/local/cargo/bin/resvg /usr/local/bin/resvg

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Persistent data volume for games and state
VOLUME ["/data"]

CMD ["python", "rengobot.py"]
