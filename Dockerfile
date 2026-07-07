FROM python:3.11-slim

WORKDIR /app

# System dependencies needed by web3 / cryptography / solc
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# torch CPU-only to keep image to a manageable size (~1.5 GB vs ~5 GB for CUDA)
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt \
    && pip install --no-cache-dir \
       torch --index-url https://download.pytorch.org/whl/cpu

# Copy application code
COPY ossverify/ ossverify/
COPY sdk/ sdk/

# Install SDK
RUN pip install --no-cache-dir -e sdk/python

EXPOSE 8000

CMD ["uvicorn", "ossverify.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
