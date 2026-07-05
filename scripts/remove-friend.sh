#!/bin/bash
# remove-friend.sh <name>
# Idempotent: deletes the entire friend namespace (cascading) and removes from registry.
set -euo pipefail

NAME="${1:?Usage: remove-friend.sh <name>}"
NS="friend-${NAME}"
HOST="${NAME}.hermes.caron.fun"

echo "→ Deleting namespace $NS (cascading: svc, deploy, pvc, secret, middleware, ir)"
kubectl delete namespace "$NS" --ignore-not-found --wait=true

# Remove from gateway registry
kubectl -n auth get configmap friends-registry -o jsonpath='{.data.friends\.json}' > /tmp/friends.json 2>/dev/null || echo '[]' > /tmp/friends.json
jq "map(select(.host != \"${HOST}\"))" /tmp/friends.json > /tmp/friends_new.json
kubectl -n auth create configmap friends-registry --from-file=friends.json=/tmp/friends_new.json --dry-run=client -o yaml | kubectl replace -f -

echo "✓ Friend $NAME removed"
rm -f /tmp/friends.json /tmp/friends_new.json
