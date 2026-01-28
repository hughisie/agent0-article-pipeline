# Multi-stage build for efficient containerization
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend
COPY agent0_gui/web/package*.json ./
RUN npm ci
COPY agent0_gui/web/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy built frontend from previous stage
COPY --from=frontend-builder /app/frontend/dist /app/agent0_gui/web/dist

# Create workspace directory
RUN mkdir -p /app/agent0_gui/workspace

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/api/health', timeout=5)"

# Run the application
CMD uvicorn agent0_gui.app:app --host 0.0.0.0 --port ${PORT}
