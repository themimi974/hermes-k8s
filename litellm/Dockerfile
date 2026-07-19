FROM python:3.11-slim

# Temp install Node.js for Prisma generation only
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "litellm[proxy]" prisma

# Generate Prisma client for litellm's schema
RUN cd /usr/local/lib/python3.11/site-packages/litellm/proxy && prisma generate

# Remove Node.js to save space/memory
RUN apt-get remove -y curl nodejs && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

EXPOSE 4000
ENTRYPOINT ["litellm"]
