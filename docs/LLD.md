# LLD — Hermes Multi-Friend Platform

**Status:** live · 2026-07-05

## 1. Per-Friend Manifests

### Namespace
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: friend-__NAME__
  labels:
    traefik: enabled
```

### ResourceQuota
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: friend-quota
  namespace: friend-__NAME__
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 1Gi
    limits.memory: 2Gi
    pods: "5"
```

### PersistentVolumeClaim
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: friend-data
  namespace: friend-__NAME__
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 2Gi
```

### Secret
```yaml
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: friend-htpasswd
  namespace: friend-__NAME__
data:
  users: __B64USERS__
```

### Middleware
```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: friend-basic
  namespace: friend-__NAME__
  labels:
    traefik: enabled
spec:
  basicAuth:
    secret: friend-htpasswd
```

### Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ttyd
  namespace: friend-__NAME__
  labels:
    app: ttyd
    friend: __NAME__
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: ttyd
      friend: __NAME__
  template:
    metadata:
      labels:
        app: ttyd
        friend: __NAME__
    spec:
      containers:
        - name: ttyd
          image: localhost/hermes-friends/ttyd:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 7681
          readinessProbe:
            tcpSocket: { port: 7681 }
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            tcpSocket: { port: 7681 }
            initialDelaySeconds: 30
            periodSeconds: 30
          resources:
            requests: { cpu: 250m, memory: 256Mi }
            limits: { cpu: 1, memory: 512Mi }
          volumeMounts:
            - name: friends-data
              mountPath: /opt/data
      volumes:
        - name: friends-data
          persistentVolumeClaim:
            claimName: friend-data
```

### Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: ttyd
  namespace: friend-__NAME__
spec:
  type: ClusterIP
  selector:
    app: ttyd
    friend: __NAME__
  ports:
    - name: ttyd
      port: 7681
      targetPort: 7681
```

### IngressRoute
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: vanity
  namespace: friend-__NAME__
spec:
  entryPoints: [websecure]
  routes:
    - match: Host(`__HOST__`)
      kind: Rule
      middlewares:
        - name: friend-basic
          namespace: friend-__NAME__
      services:
        - name: ttyd
          port: 7681
  tls:
    certResolver: cfresolver
```

**Template placeholders:** `__NAME__`, `__HOST__`, `__B64USERS__`

## 2. Dockerfile + entrypoint

```dockerfile
FROM debian:trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git tini jq htop tmux \
    && rm -rf /var/lib/apt/lists/*

# ttyd static binary (tsl0922/ttyd)
RUN curl -fsSL https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 \
      -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd

# Node 20 (for Hermes)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

# Hermes CLI
RUN curl -fsSL https://hermes.nousresearch.com/install.sh \
    | bash -s -- --skip-setup --skip-browser

EXPOSE 7681

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["ttyd", "--port", "7681", "--writable", "bash", "-l"]
```

No `entrypoint.sh` — runs as root from the Dockerfile, no gosu/privilege drop. `tini` is PID 1, reaps zombies.

## 3. add-friend.sh / remove-friend.sh

### add-friend.sh `<name> <username> <password>`

Idempotent. Creates:
1. Namespace `friend-<name>` + ResourceQuota
2. PVC `friend-data` (2Gi)
3. Secret `friend-htpasswd` (base64-encoded APR1 htpasswd)
4. Middleware `friend-basic` (basicAuth → friend-htpasswd)
5. Deployment `ttyd` (localhost/hermes-friends/ttyd:latest, Recreate)
6. Service `ttyd` (ClusterIP :7681)
7. IngressRoute `vanity` (Host(`<name>.hermes.caron.fun`) → ttyd + TLS cfresolver)
8. Updates `friends-registry` ConfigMap → syncs gateway

**Pattern:** per-friend IR (not labeled shared IR). Rationale: keeps host routing explicit (grep-friendly), no rule-priority ordering games, teardown is a single `kubectl delete ingressroute`.

### remove-friend.sh `<name>`

Deletes namespace `friend-<name>` (cascading: all resources). Removes from registry.

## 4. Gateway (hermes.caron.fun)

Static nginx pod serving an HTML page listing all friends + their subdomains + credentials. Authenticated with `hermes-basic` middleware reading `hermes-htpasswd`.

Updated by `gateway-sync.sh`: reads `friends-registry` ConfigMap → regenerates nginx ConfigMap → restarts gateway deployment.

## 5. File Layout

```
~/workspace/hermes-friends/
├── Dockerfile
├── README.md
├── REPORT.md
├── docs/
│   ├── architecture.svg
│   ├── HLD.md
│   └── LLD.md
├── manifests/
│   ├── cyprien_iov/   (8 YAMLs, real friend)
│   └── _template/     (7 YAMLs, generic placeholders)
├── gateway/
│   ├── configmap-index.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingressroute.yaml
│   └── registry.yaml
└── scripts/
    ├── add-friend.sh
    ├── remove-friend.sh
    ├── gateway-sync.sh
    └── import-image.sh
```

## 6. Runbook — Real Incidents

| Incident | Root cause | Fix |
|---|---|---|
| **kubeconfig perms** | 0600 root:root on this box (not 0640 root:wheel as originally assumed) | `chown root:admin /etc/rancher/k3s/k3s.yaml` gave group read. For non-member: copy to /tmp with loosened perms + `KUBECONFIG=/tmp/k` env var (redone each reboot) |
| **sudo -S fails in SSH shell** | Non-interactive SSH can't feed password to sudo's PAM read. `echo PASS \| sudo -S` works on this host, heredoc/printf patterns don't | Avoided entirely once kubectl stopped needing sudo (kubeconfig group fix) |
| **OIDC/oauth2-proxy dropped** | PKCE/oauth2-proxy/Keycloak was fully built, then dropped in favor of Basic Auth | Mentioned once here as history. Per-friend Basic Auth is the live approach |
| **emptyDir persistence bug** | Pod reschedule wiped /opt/data config. emptyDir doesn't survive restart | Changed to PVC (2Gi local-path). Added to deployment strategy: Recreate (not RollingUpdate) |
| **Namespace underscore rejected** | K8s namespaces must be RFC 1123 (lowercase + hyphens). `friend-cyprien_iov` rejected | Renamed to `friend-cyprien-iov`. DNS subdomain `cyprien_iov.hermes.caron.fun` kept (Cloudflare accepts underscores) |
| **Middleware @file not found** | Traefik has no file provider (only kubernetescrd). `friend-basic@file` fails | Correct: `name: friend-basic` + `namespace: friend-<name>` (CRD cross-namespace reference) |
