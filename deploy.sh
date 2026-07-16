#!/usr/bin/env bash
# hermes-k8s deploy script
# Run via: curl -fsSL <url>/deploy.sh | sudo bash
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
    if [ "$avail_gb" -lt 15 ]; then
        fail "Need ≥15GB disk, have ${avail_gb}GB"
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

# ── Docker ────────────────────────────────────────────────────
install_docker() {
    if command -v docker &>/dev/null; then
        ok "Docker already installed: $(docker --version)"
        return
    fi
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    ok "Docker installed: $(docker --version)"
}

check_compose() {
    if docker compose version &>/dev/null; then
        ok "Docker Compose: $(docker compose version --short)"
    else
        fail "Docker Compose not found"
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
    local hermes_home="${HOME}/.hermes"
    mkdir -p "$hermes_home"

    if [ -f "$hermes_home/config.yaml" ]; then
        ok "Hermes config already exists"
        return
    fi

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

    ok "Hermes configured for Ollama/Qwen"
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
    local skill_dir="${HOME}/.hermes/skills/deploy"

    if [ -d "$INSTALL_DIR/skills/deploy" ]; then
        mkdir -p "$skill_dir"
        cp -r "$INSTALL_DIR/skills/deploy/"* "$skill_dir/"
        ok "Deployment skill installed to $skill_dir"
    else
        warn "skills/deploy not found — skipping"
    fi
}

# ── k3s ───────────────────────────────────────────────────────
install_k3s() {
    if command -v k3s &>/dev/null; then
        ok "k3s already installed"
        return
    fi
    info "Installing k3s..."
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 0640" sh -
    sleep 5
    kubectl wait --for=condition=ready node --all --timeout=120s
    ok "k3s installed"
}

# ── Build Images ──────────────────────────────────────────────
build_images() {
    if [ ! -f "$INSTALL_DIR/Dockerfile" ]; then
        fail "Dockerfile not found at $INSTALL_DIR — clone failed?"
    fi

    info "Building ttyd image..."
    docker build -t localhost/hermes-friends/ttyd:latest "$INSTALL_DIR"
    docker save localhost/hermes-friends/ttyd:latest | k3s ctr images import -

    info "Building dashboard-api image..."
    docker build -t localhost/hermes-dashboard-api:latest "$INSTALL_DIR/dashboard/api"
    docker save localhost/hermes-dashboard-api:latest | k3s ctr images import -

    info "Building dashboard-frontend image..."
    docker build -t localhost/hermes-dashboard-frontend:latest "$INSTALL_DIR/dashboard/frontend"
    docker save localhost/hermes-dashboard-frontend:latest | k3s ctr images import -

    ok "All images built and imported"
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
    check_disk
    check_ram
    echo ""

    install_git
    install_docker
    check_compose
    install_ollama
    pull_model "qwen3.5:0.8b"
    install_hermes
    configure_hermes
    clone_repo
    install_k3s
    build_images
    install_deploy_skill

    echo ""
    ok "All prerequisites installed!"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Run 'hermes' to start the agent"
    echo "  2. Tell it: 'deploy hermes-k8s'"
    echo "  3. It will guide you through domain + credentials setup"
    echo ""
    echo -e "${CYAN}Repo location:${NC} $INSTALL_DIR"
    echo ""
}

main "$@"
