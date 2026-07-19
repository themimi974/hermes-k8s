#!/usr/bin/env bash
# apply-manifest.sh — substitute __DOMAIN__, __TLS__, __TLS_RESOLVER__
# in manifests, then apply via kubectl.
#
# Usage: apply-manifest.sh <manifest> <domain> <tls_method>
#   tls_method: letsencrypt | selfsigned | http
#
# Special: if <manifest> is "dashboard-api", processes
# dashboard/manifests/30-dashboard-api-deployment.yaml for DOMAIN + __TLS_RESOLVER__
#
# Examples:
#   apply-manifest.sh gateway/ingressroute.yaml hermes.example.com letsencrypt
#   apply-manifest.sh dashboard/manifests/50-ingressroute.yaml myserver.duckdns.org selfsigned
#   apply-manifest.sh dashboard-api dashboard.hermiz.duckdns.org selfsigned
set -euo pipefail

MANIFEST="${1:?Usage: apply-manifest.sh <manifest> <domain> <tls_method>}"
DOMAIN="${2:?Set domain}"
TLS_METHOD="${3:?Set tls_method: letsencrypt|selfsigned|http}"

case "$TLS_METHOD" in
    letsencrypt)
        TLS_BLOCK="certResolver: cfresolver"
        TLS_RESOLVER="cfresolver"
        ENTRYPOINTS="websecure"
        ;;
    selfsigned)
        TLS_BLOCK="secretName: hermes-tls"
        TLS_RESOLVER="hermes-tls"
        ENTRYPOINTS="websecure"
        ;;
    http)
        TLS_BLOCK=""
        TLS_RESOLVER=""
        ENTRYPOINTS="web"
        ;;
    *)
        echo "Unknown tls_method: $TLS_METHOD" >&2
        exit 1
        ;;
esac

# Build the temp file with substitutions
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

if [ "$MANIFEST" = "dashboard-api" ]; then
    # Special: substitute DOMAIN and __TLS_RESOLVER__ in dashboard-api deployment
    DASH_DEPLOY="dashboard/manifests/30-dashboard-api-deployment.yaml"
    if [ ! -f "$DASH_DEPLOY" ]; then
        echo "Error: $DASH_DEPLOY not found" >&2
        exit 1
    fi
    sed -e "s|__DOMAIN__|${DOMAIN}|g" \
        -e "s|__TLS_RESOLVER__|${TLS_RESOLVER}|g" \
        "$DASH_DEPLOY" > "$TMP"
    kubectl apply -f "$TMP"
    echo "Applied dashboard-api deployment with DOMAIN=${DOMAIN}, TLS_RESOLVER=${TLS_RESOLVER}"
elif [ "$TLS_METHOD" = "http" ]; then
    # For HTTP: remove tls block entirely + change entryPoints
    sed -e "s|__DOMAIN__|${DOMAIN}|g" \
        -e "s|entryPoints:.*\\[websecure\\]|entryPoints: [${ENTRYPOINTS}]|g" \
        -e '/^  tls:/{N;/__TLS__/d}' \
        -e "s|__TLS_RESOLVER__|${TLS_RESOLVER}|g" \
        "$MANIFEST" > "$TMP"
    kubectl apply -f "$TMP"
else
    # For HTTPS: substitute domain + replace __TLS__ and __TLS_RESOLVER__
    sed -e "s|__DOMAIN__|${DOMAIN}|g" \
        -e "s|__TLS__|${TLS_BLOCK}|g" \
        -e "s|__TLS_RESOLVER__|${TLS_RESOLVER}|g" \
        "$MANIFEST" > "$TMP"
    kubectl apply -f "$TMP"
fi
