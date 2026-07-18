#!/usr/bin/env bash
# apply-manifest.sh — substitute __DOMAIN__, __TLS__, and __TLS_RESOLVER__
# in a manifest, then apply it via kubectl.
#
# Usage: apply-manifest.sh <manifest> <domain> <tls_method>
#   tls_method: letsencrypt | selfsigned | http
#
# Examples:
#   apply-manifest.sh gateway/ingressroute.yaml hermes.example.com letsencrypt
#   apply-manifest.sh gateway/ingressroute.yaml myserver.duckdns.org selfsigned
#   apply-manifest.sh gateway/ingressroute.yaml 192.168.1.62 http
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

if [ "$TLS_METHOD" = "http" ]; then
    # For HTTP: remove tls block entirely + change entryPoints
    sed -e "s|__DOMAIN__|${DOMAIN}|g" \
        -e "s|entryPoints:.*\[websecure\]|entryPoints: [${ENTRYPOINTS}]|g" \
        -e '/^  tls:/{N;/__TLS__/d}' \
        -e "s|__TLS_RESOLVER__|${TLS_RESOLVER}|g" \
        "$MANIFEST" > "$TMP"
else
    # For HTTPS: substitute domain + replace __TLS__ and __TLS_RESOLVER__
    sed -e "s|__DOMAIN__|${DOMAIN}|g" \
        -e "s|__TLS__|${TLS_BLOCK}|g" \
        -e "s|__TLS_RESOLVER__|${TLS_RESOLVER}|g" \
        "$MANIFEST" > "$TMP"
fi

kubectl apply -f "$TMP"
