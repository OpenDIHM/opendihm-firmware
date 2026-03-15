# Stage 1: Build environment
FROM python:3.11.9-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.3.4 /uv /bin/uv

WORKDIR /app

# Copy only the files needed for installing dependencies to optimize layer caching
COPY pyproject.toml .

# Create a virtual environment and install dependencies
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install -e .

# Stage 2: Runtime environment
# Pinning the exact version as required by rules
FROM python:3.11.9-slim

# Set to non-interactive
ENV DEBIAN_FRONTEND=noninteractive

# Configuration exposed as environment variables
ENV OPENDIHM_HOST="0.0.0.0" \
    OPENDIHM_PORT="8000" \
    OPENDIHM_DEBUG="false"

# Create a non-root user 'appuser'
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Ensure the virtual environment is in the PATH
ENV PATH="/opt/venv/bin:$PATH"

# Copy source code with proper ownership
COPY --chown=appuser:appuser src/ src/

# Switch to non-root user
USER appuser

# Define the default command
CMD ["python", "-m", "opendihm_firmware"]
