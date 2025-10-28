# =====================================================
# 1️⃣ Base Image
# =====================================================
FROM python:3.10-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# =====================================================
# 2️⃣ Install System Dependencies
# =====================================================
# Minimal dependencies for ffmpeg and google client libs
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    wget \
    curl \
 && rm -rf /var/lib/apt/lists/*

# =====================================================
# 3️⃣ Copy Dependency List and Install Packages
# =====================================================
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =====================================================
# 4️⃣ Copy Application Files
# =====================================================
COPY . .

# =====================================================
# 5️⃣ Environment Variables
# =====================================================
ENV GOOGLE_CREDENTIALS_JSON=""
ENV TOKEN_PICKLE_BASE64=""
ENV PORT=8080

# =====================================================
# 6️⃣ Command to Run Your App
# =====================================================
# Option A: Flask web app
CMD ["python", "app.py"]

# If you are running Flask as an API server, uncomment instead:
# CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
