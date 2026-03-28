# Stage 1: Build Frontend
FROM node:20-slim AS builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Final Image
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser

# Create and activate virtual environment (avoids pip-as-root warning)
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Install Python dependencies inside venv
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files
COPY backend/ ./

# Copy built frontend
COPY --from=builder /app/frontend/dist ./dist

# Set ownership
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

# Bind to 0.0.0.0 explicitly
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
