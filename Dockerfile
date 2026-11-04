FROM python:3.11-slim

WORKDIR /app

# NOTE: build-essential / gcc removed — not needed after sentence-transformers was dropped.
# scikit-learn wheels ship pre-compiled for linux/amd64; no C compilation required.
# If you re-add heavy ML libraries that need native extensions, uncomment the block below:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Support dynamic PORT on Render / Cloud Run / Hugging Face
ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
