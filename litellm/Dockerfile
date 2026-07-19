FROM python:3.11-slim

# Install Node.js + libatomic1 (needed by Prisma runtime for migrations)
RUN apt-get update && apt-get install -y curl libatomic1 && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "litellm[proxy]" prisma

# Generate Prisma client for litellm's schema
RUN cd /usr/local/lib/python3.11/site-packages/litellm/proxy && prisma generate

# Keep Node.js + libatomic1 — Prisma needs them at runtime for migrate deploy

EXPOSE 4000
ENTRYPOINT ["litellm"]
