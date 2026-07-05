# hermes-k8s

Per-user isolated Hermes Agent subdomains on a single k3s node. Each friend gets their own terminal shell behind `<friend>.yourdomain.com`, with a central gateway at `yourdomain.com`.

## Architecture

See [docs/architecture.svg](docs/architecture.svg) for the precise stack diagram with real resource names.

```
Cloudflare (*.yourdomain.com → <node-ip>)
    │
    ▼
Traefik (k3s IngressRouteCRDs)
  ┌─────────┴──────────┐
  │                    │
yourdomain.com    <friend>.yourdomain.com
(gateway)         (ttyd pod)
nginx + creds     bash -l, /opt/data PVC
```

- **TLS**: Wildcard cert via Cloudflare DNS-01 challenge (automatic renewal)
- **Auth**: Per-friend basicAuth via Traefik CRD Middlewares
- **Storage**: 2Gi `local-path` PVC per friend, mounted at `/opt/data`
- **Image**: Custom `debian:trixie` + Node 20 + ttyd + Hermes Agent

---

## Prerequisites

| Requirement | Why |
|---|---|
| **Debian 12+ or Fedora 40+ VM** | k3s target |
| **Cloudflare account** with a domain | DNS-01 wildcard certs |
| **Cloudflare API Token** | Permissions: Zone > DNS > Edit (for your domain) |
| **Node IP accessible from internet** | Port 80/443 open to Cloudflare |
| **Root or sudo access** | k3s install, package management |
| **podman or docker** | Build the ttyd image |

---

## Step-by-Step Deployment

### Step 1: Clone the repo

```bash
cd ~
git clone git@github.com:themimi974/hermes-k8s.git
cd hermes-k8s
```

### Step 2: Install k3s

```bash
# Install k3s (Traefik is enabled by default)
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 0640" sh -

# Make kubectl accessible without sudo (add your user to the k3s config group)
sudo chown root:$(id -gn) /etc/rancher/k3s/k3s.yaml
# Or for a user not in the k3s group:
# sudo chmod 644 /etc/rancher/k3s/k3s.yaml

# Wait for node to be ready
kubectl get nodes --watch
# Press Ctrl+C when STATUS shows "Ready"

# Verify Traefik is running
kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik
```

### Step 3: Create the Cloudflare API token secret

```bash
# Replace with your actual Cloudflare API token
# The token needs: Zone > DNS > Edit permission for your domain
echo -n "YOUR_CLOUDFLARE_API_TOKEN" | kubectl create secret generic cloudflare-api-token \
  --from-literal=CF_DNS_API_TOKEN=/dev/stdin \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Step 4: Configure Traefik with Cloudflare DNS-01

```bash
# Replace YOUR_EMAIL with your Cloudflare account email
cat <<'EOF' | kubectl apply -f -
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: traefik
  namespace: kube-system
spec:
  chart: traefik
  repo: https://traefik.github.io/charts
  version: 40.1.3
  valuesContent: |-
    providers:
      kubernetesCRD:
        enabled: true
        allowEmptyServices: true
      kubernetesIngress:
        enabled: true
        allowEmptyServices: true
    entryPoints:
      web:
        port: 8000
      websecure:
        port: 8443
        http:
          tls:
            certResolver: cfresolver
    certificatesResolvers:
      cfresolver:
        acme:
          email: YOUR_EMAIL
          dnsChallenge:
            provider: cloudflare
            envFromSecret: cloudflare-api-token
          storage: /data/acme.json
    logs:
      access:
        enabled: true
        fields:
          headers:
            names:
              X-Forwarded-Proto: keep
              X-Forwarded-Host: keep
              X-Forwarded-For: keep
EOF

# Wait for Traefik to pick up the new config
kubectl -n kube-system rollout status deployment/traefik --timeout=120s
```

### Step 5: Configure DNS in Cloudflare

In your Cloudflare dashboard, add these DNS records:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | `<node-ip>` | DNS only (gray cloud) |
| A | `*` | `<node-ip>` | DNS only (gray cloud) |

> **Important**: Use "DNS only" (gray cloud), not "Proxied" (orange cloud).
> Traefik handles TLS termination; Cloudflare should not proxy the traffic.

### Step 6: Build and import the ttyd image

```bash
# Install podman if not present
# Debian: sudo apt install podman
# Fedora: sudo dnf install podman

# Build the image (takes ~2-3 minutes on first build)
podman build -t hermes-friends/ttyd:latest .

# Export and import into k3s containerd (needs sudo for the k3s socket)
podman save hermes-friends/ttyd:latest | sudo k3s ctr images import -

# Verify
sudo k3s ctr images list | grep ttyd
# Should show: localhost/hermes-friends/ttyd:latest
```

### Step 7: Create the auth namespace + gateway htpasswd

```bash
kubectl create namespace auth

# Create the gateway htpasswd secret (replace admin:Test1234 with your own)
# Generate the hash: openssl passwd -apr1 -salt mysalt yourpassword
GW_HASH=$(openssl passwd -apr1 -salt gateway AdminPass123)
echo -n "admin:$GW_HASH" | kubectl create secret generic hermes-htpasswd \
  --from-literal=users=/dev/stdin \
  --namespace=auth \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Step 8: Apply the gateway

```bash
# Replace hermes.caron.fun with your actual domain
sed -i 's/hermes\.caron\.fun/YOUR_DOMAIN/g' gateway/ingressroute.yaml

kubectl apply -f gateway/

# Wait for nginx to start
kubectl -n auth rollout status deployment/gateway --timeout=60s
```

### Step 9: Add your first friend

```bash
bash scripts/add-friend.sh alice alice 'your-password'
```

This creates everything in one go:
- Namespace `friend-alice`
- PersistentVolumeClaim (2Gi)
- htpasswd Secret
- Traefik Middleware (basicAuth)
- Deployment (ttyd pod)
- Service (ClusterIP :7681)
- IngressRoute (`alice.yourdomain.com` → ttyd:7681 + TLS)
- Updates gateway registry

### Step 10: Update manifests for your domain

Replace the domain in the cyprien_iov manifests (or any friend manifests):

```bash
sed -i 's/hermes\.caron\.fun/YOUR_DOMAIN/g' manifests/*/07-ingressroute.yaml
sed -i 's/hermes\.caron\.fun/YOUR_DOMAIN/g' manifests/_template/06-ingressroute.yaml
sed -i 's/hermes\.caron\.fun/YOUR_DOMAIN/g' gateway/ingressroute.yaml
```

### Step 11: Verify everything works

```bash
# Test the friend endpoint (expect 401 first)
curl -sk -o /dev/null -w "%{http_code}" https://alice.YOUR_DOMAIN/
# 401

# Test with credentials (expect 200 + ttyd HTML)
curl -sk -u 'alice:your-password' https://alice.YOUR_DOMAIN/
# 200 (ttyd HTML)

# Test the gateway (expect 401)
curl -sk -o /dev/null -w "%{http_code}" https://YOUR_DOMAIN/
# 401

# Test the gateway with credentials (expect 200)
curl -sk -u 'admin:AdminPass123' https://YOUR_DOMAIN/
# 200 (landing page)
```

---

## Adding More Friends

```bash
# Add a friend
bash scripts/add-friend.sh <name> <username> <password>

# Example
bash scripts/add-friend.sh bob bob 'hunter2'

# Update gateway to show the new friend
bash scripts/gateway-sync.sh
```

Each friend gets:
- Their own subdomain: `<name>.yourdomain.com`
- Their own Kubernetes namespace: `friend-<name>`
- Their own persistent storage: 2Gi PVC at `/opt/data`
- Their own Traefik basicAuth middleware

---

## Removing a Friend

```bash
bash scripts/remove-friend.sh bob
```

This deletes:
- Namespace `friend-bob` (cascading: all resources inside)
- Removes from gateway registry
- Restarts gateway

---

## Persistence Test

Files in `/opt/data` survive pod restarts:

```bash
# Write a test file
kubectl -n friend-alice exec deployment/ttyd -- sh -c 'echo "test" > /opt/data/.test'

# Kill the pod
kubectl -n friend-alice delete pod -l app=ttyd

# After respawn (~10s), verify
kubectl -n friend-alice exec deployment/ttyd -- cat /opt/data/.test
# Should output: test
```

---

## Troubleshooting

### Traefik shows "middleware does not exist"

Ensure your IngressRoute references middlewares with `name` + `namespace`:

```yaml
# Correct (CRD middleware)
middlewares:
  - name: friend-basic
    namespace: friend-alice

# Wrong (file provider, won't work)
middlewares:
  - name: friend-basic@file
```

### Pod stuck in ImagePullBackOff

The image is local-only. Ensure:
1. Image was imported: `sudo k3s ctr images list | grep ttyd`
2. Deployment uses `localhost/` prefix and `imagePullPolicy: Never`

### TLS cert not issuing

Check Traefik logs:
```bash
kubectl -n kube-system logs deployment/traefik --tail=50 | grep -i acme
```

Common issues:
- Cloudflare API token doesn't have DNS:Edit permission
- DNS record not set to "DNS only" (gray cloud)
- Email in HelmChart doesn't match Cloudflare account

### Namespace creation fails with "invalid"

Kubernetes namespace names must be lowercase alphanumeric + hyphens only. No underscores.

### PVC won't mount

Check PVC status:
```bash
kubectl -n friend-alice get pvc friend-data
```

If stuck in Pending, ensure `local-path` StorageClass exists:
```bash
kubectl get storageclass
```

---

## File Layout

```
hermes-k8s/
├── README.md                    ← this file
├── REPORT.md                    ← project report
├── Dockerfile                   ← ttyd image build
├── .gitignore                   ← excludes secrets
├── manifests/
│   ├── cyprien_iov/             ← first-friend example (8 YAMLs)
│   └── _template/               ← generic template for add-friend.sh
├── gateway/                     ← yourdomain.com landing page
│   ├── configmap-index.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingressroute.yaml
│   └── registry.yaml
└── scripts/
    ├── add-friend.sh            ← idempotent full provision
    ├── remove-friend.sh         ← teardown
    ├── gateway-sync.sh          ← registry → nginx
    └── import-image.sh          ← podman → k3s containerd
```

---

## Security Notes

- **No credentials in repo**: htpasswd secrets are sanitized before commit
- **Test environment**: credential rotation not implemented (by design)
- **TLS everywhere**: Traefik terminates TLS, traffic inside cluster is unencrypted (localhost only)
- **Cloudflare token**: stored in Kubernetes Secret, not in repo
