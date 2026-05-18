# FILE: Dockerfile

# --- Stage 1: Build Stage ---
FROM python:3.11-slim as builder
WORKDIR /app
RUN pip install --upgrade pip
COPY ./app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Final Stage ---
FROM python:3.11-slim
WORKDIR /app

# Copy installed packages and executables
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create a non-root user and set permissions for deployment
RUN useradd -m appuser
RUN mkdir -p /data/huggingface_cache && chown -R appuser:appuser /app /data
USER appuser

# Copy the application source code
COPY . .
RUN pip install --no-cache-dir -e .

# Expose the port for the hosting environment
EXPOSE 7860

# Define the production command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]