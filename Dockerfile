# Multi-stage Dockerfile for WoW Combat Log Parser
# Stage 1: Builder - Install dependencies and build environment
FROM python:3.11-slim AS builder

LABEL maintainer="WoW Combat Log Parser Team"
LABEL description="World of Warcraft combat log parser and streaming server"

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Create minimal production image
FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd -g $GROUP_ID appuser && useradd -u $USER_ID -g $GROUP_ID -r appuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code
COPY src/ ./src/
COPY migrations/ ./migrations/

# Create directories for data and logs with proper permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app && \
    chmod 755 /app/data /app/logs

# Copy Docker entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Note: We start as root and switch to appuser in entrypoint script
# This allows us to set up volumes with correct permissions

# Health check endpoint (unified server)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default environment variables
ENV DB_PATH=/app/data/combat_logs.db
ENV LOG_LEVEL=info
ENV HOST=0.0.0.0
ENV PORT=8000

# Use entrypoint script for initialization
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command to run the unified server (streaming + REST API v1)
CMD ["python", "-m", "src.api.app"]