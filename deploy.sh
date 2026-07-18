#!/usr/bin/env bash
# hermes-k8s deploy script
# Run via: curl -fsSL https://raw.githubusercontent.com/themimi974/hermes-k8s/main/deploy.sh | sudo bash
# Or: sudo bash deploy.sh (from inside the repo)
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

REPO_URL="https://github.com/themimi974/hermes-k8s.git"
INSTALL_DIR="/opt/hermes-k8s"
USE_LOCAL_MODEL=""
USE_NIM=""
NVIDIA_API_KEY=""

# ── OS Detection ──────────────────────────────────────────────
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID}"
        OS_VERSION="${VERSION_ID}"
        OS_FAMILY=""
        case "$ID" in
            ubuntu|debian|linuxmint|pop) OS_FAMILY="debian" ;;
            fedora|rhel|centos|rocky|alma|ol) OS_FAMILY="rhel" ;;
            arch|manjaro) OS_FAMILY="arch" ;;
            *) fail "Unsupported OS: $ID" ;;
        esac
    else
        fail "Cannot detect OS — /etc/os-release not found"
    fi
    info "Detected: $PRETTY_NAME (family: $OS_FAMILY)"
}

# ── Detect real user (not root) ───────────────────────────────
detect_real_user() {
    REAL_USER="${SUDO_USER:-$USER}"
    REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
    info "Running as root, configuring for user: $REAL_USER ($REAL_HOME)"
}

# ── Checks ───────────────────────────────────────────────────
check_root() {
    if [ "$EUID" -ne 0 ]; then
        fail "Run as root: sudo bash deploy.sh"
    fi
}

check_disk() {
    local avail_kb
    avail_kb=$(df / --output=avail | tail -1 | tr -d ' ')
    local avail_gb=$((avail_kb / 1048576))
    if [ "$avail_gb" -lt 10 ]; then
        fail "Need ≥10GB disk, have ${avail_gb}GB"
    fi
    ok "Disk: ${avail_gb}GB available"
}

check_ram() {
    local ram_mb
    ram_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
    if [ "$ram_mb" -lt 3500 ]; then
        fail "Need ≥4GB RAM, have ${ram_mb}MB"
    fi
    ok "RAM: ${ram_mb}MB"
}

# ── Interactive: Local Model? ─────────────────────────────────
ask_local_model() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Would you like to use a local model (Ollama + Qwen)?  ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  ${GREEN}Yes${NC} — Install Ollama + pull qwen3.5:0.8b (runs on your machine)"
    echo "  ${YELLOW}No${NC}  — Use a cloud provider (OpenRouter, Anthropic, etc.)"
    echo ""
    while true; do
        read -rp "$(echo -e "${CYAN}Use local model? [Y/n]: ${NC}")" answer </dev/tty
        case "${answer,,}" in
            y|yes|"") USE_LOCAL_MODEL="yes"; break ;;
            n|no)     USE_LOCAL_MODEL="no";  break ;;
            *) echo "  Please answer y or n" ;;
        esac
    done
    echo ""
}

# ── Interactive: NVIDIA NIM? ──────────────────────────────────
ask_nvidia_nim() {
    # Only ask if user declined local model
    if [ "$USE_LOCAL_MODEL" = "yes" ]; then return; fi

    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Use NVIDIA NIM? (free cloud inference)                ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  ${GREEN}Yes${NC} — NVIDIA NIM (free tier, default: deepseek-ai/deepseek-v4-pro)"
    echo "  ${YELLOW}No${NC}  — I'll configure my own provider later"
    echo ""
    echo -e "  ${CYAN}You'll need a free API key from https://build.nvidia.com${NC}"
    echo -e "  (Sign up → Generate API Key → copy the nvapi-... value)"
    echo ""
    while true; do
        read -rp "$(echo -e "${CYAN}Use NVIDIA NIM? [Y/n]: ${NC}")" answer </dev/tty
        case "${answer,,}" in
            y|yes|"")
                USE_NIM="yes"
                echo ""
                read -rp "$(echo -e "${CYAN}NVIDIA API key (nvapi-...): ${NC}")" NVIDIA_API_KEY </dev/tty
                if [ -z "$NVIDIA_API_KEY" ]; then
                    warn "No key provided — you'll need to set NVIDIA_API_KEY before running hermes"
                fi
                break
                ;;
            n|no)     USE_NIM="no";  break ;;
            *) echo "  Please answer y or n" ;;
        esac
    done
    echo ""
}

# ── Podman (daemonless — no conflict with k3s networking) ──────
install_podman() {
    if command -v podman &>/dev/null; then
        ok "Podman already installed: $(podman --version)"
        return
    fi
    info "Installing podman..."
    case "$OS_FAMILY" in
        debian) apt-get update -qq && apt-get install -y -qq podman ;;
        rhel)   dnf install -y -q podman ;;
        arch)   pacman -S --noconfirm podman ;;
    esac
    ok "Podman installed: $(podman --version)"
}

# ── Prevent Docker (conflicts with k3s networking) ────────────
check_no_docker() {
    if command -v docker &>/dev/null; then
        warn "Docker detected — it conflicts with k3s networking (cni0 corruption)"
        warn "Run 'systemctl disable --now docker docker.socket' if you see network issues"
    fi
}

# ── Git ───────────────────────────────────────────────────────
install_git() {
    if command -v git &>/dev/null; then
        ok "Git: $(git --version)"
        return
    fi
    info "Installing git..."
    case "$OS_FAMILY" in
        debian) apt-get update -qq && apt-get install -y -qq git ;;
        rhel)   dnf install -y -q git ;;
        arch)   pacman -S --noconfirm git ;;
    esac
    ok "Git installed"
}

# ── Ollama ────────────────────────────────────────────────────
install_ollama() {
    if command -v ollama &>/dev/null; then
        ok "Ollama already installed"
        return
    fi
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    systemctl enable --now ollama
    sleep 3
    ok "Ollama installed"
}

pull_model() {
    local model="${1:-qwen3.5:0.8b}"
    if ollama list 2>/dev/null | grep -q "$model"; then
        ok "Model already pulled: $model"
        return
    fi
    info "Pulling model: $model (this may take a few minutes)..."
    ollama pull "$model"
    ok "Model ready: $model"
}

check_ollama() {
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        ok "Ollama is up on :11434"
    else
        warn "Ollama not responding on :11434 — you may need to run: ollama serve"
    fi
}

# ── Hermes Agent ──────────────────────────────────────────────
install_hermes() {
    if command -v hermes &>/dev/null; then
        ok "Hermes Agent already installed"
        return
    fi
    info "Installing Hermes Agent..."
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser
    ok "Hermes Agent installed"
}

configure_hermes() {
    local hermes_home="/root/.hermes"
    mkdir -p "$hermes_home"

    if [ -f "$hermes_home/config.yaml" ]; then
        info "Hermes config exists — backing up before overwrite"
        cp "$hermes_home/config.yaml" "$hermes_home/config.yaml.bak.$(date +%s)"
    fi

    if [ "$USE_LOCAL_MODEL" = "yes" ]; then
        info "Configuring Hermes Agent for Ollama/Qwen..."

        cat > "$hermes_home/config.yaml" << 'YAML'
model:
  default: qwen3.5:0.8b
  provider: custom
  base_url: http://localhost:11434/v1
  api_key: ollama
  context_length: 8192

agent:
  max_turns: 90

terminal:
  backend: local
  timeout: 300

compression:
  enabled: true

memory:
  memory_enabled: true
  user_profile_enabled: true
YAML

        # Also write .env for env-var-based setups
        cat > "$hermes_home/.env" << 'ENV'
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama
MODEL_PROVIDER=ollama
ENV

        ok "Hermes configured for Ollama/Qwen (local model)"

    elif [ "$USE_NIM" = "yes" ]; then
        info "Configuring Hermes Agent for NVIDIA NIM..."
        info "Default model: deepseek-ai/deepseek-v4-pro (free)"

        cat > "$hermes_home/config.yaml" << 'YAML'
model:
  default: deepseek-ai/deepseek-v4-pro
  provider: nvidia
  context_length: 131072

agent:
  max_turns: 90

terminal:
  backend: local
  timeout: 300

compression:
  enabled: true

memory:
  memory_enabled: true
  user_profile_enabled: true
YAML

        # Write NVIDIA API key to .env
        if [ -n "$NVIDIA_API_KEY" ]; then
            cat > "$hermes_home/.env" << ENVEOF
NVIDIA_API_KEY=$NVIDIA_API_KEY
ENVEOF
            ok "NVIDIA API key written to $hermes_home/.env"

            # Also create litellm-credentials secret with the real key
            # (so litellm pod gets it via envFrom)
            if command -v kubectl &>/dev/null && kubectl get ns litellm &>/dev/null 2>&1; then
                kubectl create secret generic litellm-credentials -n litellm \
                    --from-literal=NVIDIA_API_KEY="$NVIDIA_API_KEY" \
                    --from-literal=LITELLM_MASTER_KEY="sk-master-$(openssl rand -hex 24)" \
                    --dry-run=client -o yaml | kubectl apply -f -
                ok "litellm-credentials secret updated with NVIDIA key"
            fi
        else
            warn "No NVIDIA API key — set it before running hermes:"
            echo -e "  ${GREEN}sudo hermes config set NVIDIA_API_KEY nvapi-your-key${NC}"
        fi

        ok "Hermes configured for NVIDIA NIM (deepseek-ai/deepseek-v4-pro)"
        echo -e "  To change model later, run: ${GREEN}sudo hermes model${NC}"
        echo ""

    else
        info "Skipping model config — you'll configure Hermes later"
        echo ""
        echo -e "  Run ${GREEN}hermes setup${NC} to configure your provider and API key"
        echo -e "  Then ${GREEN}hermes model${NC} to select your model"
        echo ""
    fi
}

# ── Clone Repo ────────────────────────────────────────────────
clone_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        ok "Repo already cloned at $INSTALL_DIR"
        cd "$INSTALL_DIR"
        git pull --ff-only 2>/dev/null || true
        return
    fi
    info "Cloning hermes-k8s..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "Repo cloned to $INSTALL_DIR"
}

# ── Skills ────────────────────────────────────────────────────
install_deploy_skill() {
    local skill_dir="/root/.hermes/skills/deploy"

    if [ -d "$INSTALL_DIR/skills/deploy" ]; then
        mkdir -p "$skill_dir"
        cp -r "$INSTALL_DIR/skills/deploy/"* "$skill_dir/"
        ok "Deployment skill installed to $skill_dir"
    else
        warn "skills/deploy not found — skipping"
    fi
}

# ── Firewalld (Fedora/RHEL) ────────────────────────────────────
fix_firewalld() {
    if ! command -v firewall-cmd &>/dev/null; then return; fi
    if ! systemctl is-active --quiet firewalld 2>/dev/null; then
        ok "Firewalld not active — skipping"
        return
    fi
    info "Firewalld detected — trusting k3s bridge interfaces..."
    firewall-cmd --zone=trusted --add-interface=cni0 --permanent 2>/dev/null || true
    firewall-cmd --zone=trusted --add-interface=flannel.1 --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    ok "Firewalld: cni0 + flannel.1 trusted"
}

# ── k3s ───────────────────────────────────────────────────────
install_k3s() {
    if command -v k3s &>/dev/null; then
        ok "k3s already installed"
        return
    fi
    info "Installing k3s..."
    # --disable-network-policy: single-node deploys don't need kube-router netpol.
    # Without this, kube-router programs iptables REJECT rules that block
    # pod-to-pod traffic across namespaces, causing 502/no-route-to-host.
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 0640 --disable-network-policy" sh -
    sleep 5
    kubectl wait --for=condition=ready node --all --timeout=120s
    ok "k3s installed"
}

# ── Build Images (podman → k3s containerd) ─────────────────────
build_images() {
    if [ ! -f "$INSTALL_DIR/Dockerfile" ]; then
        fail "Dockerfile not found at $INSTALL_DIR — clone failed?"
    fi

    info "Building ttyd image..."
    podman build --no-cache -t localhost/hermes-friends/ttyd:latest "$INSTALL_DIR"

    info "Building dashboard-api image..."
    podman build --no-cache -t localhost/hermes-dashboard-api:latest "$INSTALL_DIR/dashboard/api"

    info "Building dashboard-frontend image..."
    podman build --no-cache -t localhost/hermes-dashboard-frontend:latest "$INSTALL_DIR/dashboard/frontend"

    info "Building litellm image..."
    podman build --no-cache -t localhost/hermes-litellm:latest "$INSTALL_DIR/litellm"

    ok "All images built"
}

import_to_k3s() {
    info "Importing images into k3s containerd..."
    for img in hermes-friends/ttyd hermes-dashboard-api hermes-dashboard-frontend hermes-litellm; do
        podman save "localhost/$img:latest" | k3s ctr images import -
    done
    ok "All images imported to k3s"
}

# ── Main ──────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     hermes-k8s deploy script         ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
    echo ""

    detect_os
    check_root
    detect_real_user
    check_disk
    check_ram
    echo ""

    # Ask user about model provider BEFORE installing anything
    ask_local_model
    ask_nvidia_nim

    install_git
    install_podman
    check_no_docker

    if [ "$USE_LOCAL_MODEL" = "yes" ]; then
        install_ollama
        pull_model "qwen3.5:0.8b"
        check_ollama
    fi

    install_hermes
    configure_hermes
    clone_repo
    fix_firewalld
    install_k3s
    build_images
    import_to_k3s
    install_deploy_skill

    echo ""
    ok "All prerequisites installed!"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Run 'sudo hermes' to start the agent (root is required —"
    echo "     Hermes config and k3s access both live under /root)"
    echo "  2. Tell it: 'deploy hermes-k8s'"
    echo "  3. It will guide you through domain + credentials setup"
    echo ""
    echo -e "${CYAN}Repo location:${NC} $INSTALL_DIR"
    echo ""
}

main "$@"
