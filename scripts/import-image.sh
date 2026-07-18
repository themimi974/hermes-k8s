#!/bin/bash
# Push podman-built images into k3s containerd
# Run interactively: bash scripts/import-image.sh
set -euo pipefail

IMAGES=(
    "localhost/hermes-friends/ttyd:latest"
    "localhost/hermes-dashboard-api:latest"
    "localhost/hermes-dashboard-frontend:latest"
    "localhost/hermes-litellm:latest"
)

for img in "${IMAGES[@]}"; do
    echo "Importing $img..."
    podman save "$img" | sudo k3s ctr images import -
    echo "✓ $img imported"
done

echo ""
echo "Verifying:"
sudo k3s ctr images list | grep -E "hermes-|ttyd"
