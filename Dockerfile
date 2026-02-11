# ============================================
# DocAI RAG Application - Dockerfile
# ============================================
# Multi-stage build for optimized image size
# ============================================

# ============================================
# Stage 1: Builder - Install dependencies
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 2: Runtime - Production image
# ============================================
FROM python:3.11-slim AS runtime

# Set labels
LABEL maintainer="DocAI Team"
LABEL version="1.0.0"
LABEL description="DocAI RAG Application"

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY app/ ./app/
COPY main.py .
COPY template/ ./template/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY libs/ ./libs/

# Create necessary directories
RUN mkdir -p /app/uploadfiles/pdf \
             /app/uploadfiles/docx \
             /app/uploadfiles/pptx \
             /app/uploadfiles/txt \
             /app/uploadfiles/md \
             /app/data/faiss_indices/files \
             /app/data/faiss_indices/skills \
             /app/logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8082/ || exit 1

# Default command
CMD ["python", "main.py"]
