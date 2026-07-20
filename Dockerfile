FROM debian:trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git tini jq htop tmux \
    && rm -rf /var/lib/apt/lists/*

# ttyd static binary
RUN curl -fsSL https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
      -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd

# Node 24 (required by agent-browser / Hermes browser tools)
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

# Hermes CLI (skip interactive setup)
RUN curl -fsSL https://hermes.nousresearch.com/install.sh \
    | bash -s -- --skip-setup --skip-browser

EXPOSE 7681

# tini as PID 1; entrypoint: ttyd serves bash -l on :7681
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["ttyd", "--port", "7681", "--writable", "bash", "-l"]
