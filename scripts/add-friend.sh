#!/bin/bash
# add-friend.sh <name> <username> <password>
# Idempotent: creates namespace, secret, middleware, PVC, deployment, service,
# ingressroute for a new friend, then updates the gateway registry.
set -euo pipefail

NAME="${1:?Usage: add-friend.sh <name> <username> <password>}"
USER="${2:?Usage: add-friend.sh <name> <username> <password>}"
PASS="${3:?Usage: add-friend.sh <name> <username> <password>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFESTS="$SCRIPT_DIR/../manifests/_template"
NS="friend-${NAME}"
HOST="${NAME}.hermes.caron.fun"
KUBECTL="kubectl"

# Generate htpasswd entry (APR1/MD5)
B64USERS=$(htpasswd -nbm -c /dev/stdout "$USER" "$PASS" | base64 -w0)
# Also base64 without wrapping (some kubectl versions are picky)
B64USERS_NW=$(echo -n "${USER}:$(htpasswd -nbm /dev/stdout "$USER" "$PASS" | cut -d: -f2-)" | base64 -w0)

echo "→ Creating namespace $NS"
for f in 00-namespace.yaml 01-data-pvc.yaml 02-htpasswd.yaml 03-middleware.yaml 04-deployment.yaml 05-service.yaml 06-ingressroute.yaml; do
  sed -e "s|__NAME__|${NAME}|g" \
      -e "s|__HOST__|${HOST}|g" \
      -e "s|__B64USERS__|${B64USERS_NW}|g" \
      "$MANIFESTS/$f" | $KUBECTL apply -f -
done

echo "→ Waiting for deployment rollout"
$KUBECTL -n "$NS" rollout status deployment/ttyd --timeout=120s || true

echo "✓ Friend $NAME provisioned → https://${HOST}/"

# Update gateway registry (if it exists)
$KUBECTL -n auth get configmap friends-registry -o jsonpath='{.data.friends\.json}' > /tmp/friends.json 2>/dev/null || echo '[]' > /tmp/friends.json

# Add entry (idempotent: remove existing host entry first)
jq "map(select(.host != \"${HOST}\")) + [{\"host\":\"${HOST}\",\"user\":\"${USER}\",\"pass\":\"${PASS}\",\"namespace\":\"${NS}\"}]" /tmp/friends.json > /tmp/friends_new.json
$KUBECTL -n auth create configmap friends-registry --from-file=friends.json=/tmp/friends_new.json --dry-run=client -o yaml | $KUBECTL replace -f -

echo "✓ Registry updated"
rm -f /tmp/friends.json /tmp/friends_new.json
