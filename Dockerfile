# Multi-stage GPU-enabled Dockerfile for Drug Design Agent Backend
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Avoid prompt during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

# Install system dependencies & Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    libxrender1 \
    libxext6 \
    build-essential \
    curl \
    git \
    autodock-vina \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create virtualenv
RUN python3.10 -m venv /opt/venv

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code & data
COPY app ./app
COPY source_backup ./source_backup
COPY data ./data
COPY demo_data ./demo_data
COPY scripts ./scripts
COPY .env.example .env

# Expose FastAPI default port
EXPOSE 8000

# Default launch command
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
