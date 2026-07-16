# OS Compatibility Matrix

## Supported Operating Systems

| Family | Distro | Min Version | Package Manager | Status |
|--------|--------|-------------|-----------------|--------|
| **Debian** | Ubuntu | 22.04 LTS | apt | ✅ Tested |
| **Debian** | Debian | 12 (Bookworm) | apt | ✅ Tested |
| **Debian** | Linux Mint | 21+ | apt | ✅ Should work |
| **Debian** | Pop!_OS | 22.04+ | apt | ✅ Should work |
| **RHEL** | Fedora | 40+ | dnf | ✅ Tested |
| **RHEL** | RHEL | 9+ | dnf/yum | ✅ Should work |
| **RHEL** | Rocky Linux | 9+ | dnf/yum | ✅ Should work |
| **RHEL** | AlmaLinux | 9+ | dnf/yum | ✅ Should work |
| **RHEL** | CentOS Stream | 9+ | dnf/yum | ✅ Should work |
| **Arch** | Arch Linux | rolling | pacman | ⚠️ Untested |
| **Arch** | Manjaro | recent | pacman | ⚠️ Untested |

## Minimum Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| Network | Public IP | Cloudflare-proxied domain |

## Per-OS Notes

### Ubuntu/Debian

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh

# Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Git (if not present)
sudo apt update && sudo apt install -y git
```

### Fedora/RHEL

```bash
# Docker
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# OR use the convenience script
curl -fsSL https://get.docker.com | sudo sh

# Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Git
sudo dnf install -y git
```

### Arch/Manjaro

```bash
# Docker
sudo pacman -S docker docker-compose
sudo systemctl enable --now docker

# Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Git
sudo pacman -S git
```

## Known Issues

- **Ubuntu 20.04**: Docker version too old, upgrade to 22.04+
- **RHEL 8**: Ollama may need manual install, check ollama.com
- **ARM64**: Supported but images may be slower to build
- **WSL2**: Works but networking between WSL and Windows needs extra config
