FROM python:3.10-slim

# Install curl, Node.js, and npm
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Railway automatically sets and exposes the PORT environment variable
EXPOSE 5000

CMD ["sh", "-c", "gunicorn -k gthread -w 1 --threads 8 --bind 0.0.0.0:${PORT:-5000} --timeout 120 app:app"]
