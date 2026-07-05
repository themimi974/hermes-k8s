#!/bin/bash
# Push the podman-built ttyd image into k3s containerd
# Run interactively: bash ~/workspace/hermes-friends/scripts/import-image.sh
set -euo pipefail
podman save hermes-friends/ttyd:latest | sudo k3s ctr images import -
echo "✓ Image hermes-friends/ttyd:latest imported into k3s"
sudo k3s ctr images list | grep ttyd
