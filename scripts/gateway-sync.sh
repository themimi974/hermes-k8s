#!/bin/bash
# gateway-sync.sh
# Reads friends-registry ConfigMap, generates nginx configmap, restarts gateway.
set -euo pipefail

# Fetch current registry
kubectl -n auth get configmap friends-registry -o jsonpath='{.data.friends\.json}' > /tmp/friends.json 2>/dev/null || echo '[]' > /tmp/friends.json

# Read existing index.html template (the one from gateway/configmap-index.yaml)
# We inject the friends array as a JS variable
TEMPLATE=$(cat "$(dirname "$0")/../gateway/configmap-index.yaml" | sed -n '/index.html:/,$ p' | tail -n +2)
FRIENDS_JSON=$(cat /tmp/friends.json)

# Build the final HTML by injecting the friends array
FINAL_HTML=$(echo "$TEMPLATE" | sed "s|window.__FRIENDS__ || \[\]|window.__FRIENDS__ = ${FRIENDS_JSON}|")

# Write to temp file
echo "$FINAL_HTML" > /tmp/gateway-index.html

# Update the ConfigMap
kubectl -n auth create configmap gateway-index --from-file=index.html=/tmp/gateway-index.html --dry-run=client -o yaml | kubectl replace -f -

# Restart gateway to pick up new configmap
kubectl -n auth rollout restart deployment/gateway

echo "✓ Gateway synced with $(echo "$FRIENDS_JSON" | jq length) friend(s)"

rm -f /tmp/friends.json /tmp/gateway-index.html
