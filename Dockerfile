FROM debian:trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git tini jq htop tmux make g++ python3 \
    && rm -rf /var/lib/apt/lists/*

# ttyd static binary
RUN curl -fsSL https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
      -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd

# Node 24 (required by agent-browser / Hermes browser tools)
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

# Hermes CLI (skip interactive setup, install browser tools)
RUN curl -fsSL https://hermes.nousresearch.com/install.sh \
    | bash -s -- --skip-setup

# Install browser system dependencies + agent-browser + Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
      libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 \
      libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
      libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 \
      libatspi2.0-0t64 libxshmfence1 fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && cd /usr/local/lib/hermes-agent && npm install agent-browser@latest \
    && npx agent-browser install

EXPOSE 7681

# tini as PID 1; entrypoint: ttyd serves bash -l on :7681
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["ttyd", "--port", "7681", "--writable", "bash", "-l"]
