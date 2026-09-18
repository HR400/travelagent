# Production Dockerfile for ReAct Travel Agent
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install dependencies first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appgroup *.py ./
COPY --chown=appuser:appgroup tests/ ./tests/
COPY --chown=appuser:appgroup travel_profile.json ./

# Switch to non-root user
USER appuser

# Default command
CMD ["python", "main.py"]

# Health check endpoint (runs config validation)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python main.py --validate-config || exit 1
