# Web Dashboard Design Document

> **Version:** 2.0 (revised after review)
> **Date:** 2026-07-05
> **Repository:** github.com/themimi974/hermes-k8s
> **Status:** Design phase — not yet implemented
> **Supersedes:** shell scripts for friend management (add-friend.sh, remove-friend.sh, gateway-sync.sh)

---

## 1. Current State Summary

**What exists today:**
- 2 friends provisioned: `friend-cyprien-iov`, `friend-abricot`
- Each has: namespace, PVC (2Gi), ttyd Deployment, Service, IngressRoute + basicAuth Middleware
- 1 gateway at `hermes.caron.fun` (nginx landing page with friend list)
- Management via shell scripts: `add-friend.sh`, `remove-friend.sh`, `gateway-sync.sh`
- Traefik IngressRouteCRDs with Cloudflare DNS-01 wildcard TLS
- `local-path` StorageClass (no VolumeSnapshot support)

**What we're building:**
A web dashboard that replaces shell scripts with a browser UI for managing friends, viewing status, and saving/restoring Hermes state — while keeping the same k8s resource structure underneath.

---

## 2. Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend** | React + Vite + TailwindCSS + shadcn/ui | Fast iteration, great DX, component library |
| **Backend API** | Python 3.11+ FastAPI | Native async, `kubernetes` Python client, auto-generated OpenAPI docs |
| **Database** | SQLite (POC) → PostgreSQL (prod) | Zero-config for POC; easy migration later |
| **Object Storage** | MinIO (in-cluster) | S3-compatible, single binary, runs as Deployment + PVC |
| **Auth** | **BasicAuth at Traefik level** (same as existing ttyd endpoints) | No JWT, no OAuth, no separate auth layer. Dashboard runs behind `hermes-basic` middleware |
| **Image Registry** | Existing podman → k3s containerd flow | No change to current image pipeline |
| **Reverse Proxy** | Existing Traefik | Dashboard gets its own IngressRoute behind `hermes-basic` |

**Why not alternatives:**
- *Go + client-go:* Faster runtime but slower iteration for POC. Python `kubernetes` client is mature enough.
- *Next.js:* Overkill for a dashboard. React SPA served by nginx is simpler.
- *Keycloak/OIDC/JWT:* Adds 500Mi+ RAM and complexity. BasicAuth is already deployed and confirmed working. For a 5–10 friend test environment, a separate auth layer adds nothing.
- *PostgreSQL:* Extra PVC + StatefulSet for a POC. SQLite embedded in the API container.
- *Velero:* Requires restic + MinIO anyway, doesn't work well with local-path. Custom tar approach is simpler.

---

## 3. Component Diagram

```
                         ┌─────────────────────────────────────────┐
                         │            dashboard namespace          │
                         │                                         │
Internet ──HTTPS──► Traefik ──► dashboard-frontend (nginx)        │
                         │         │                               │
                         │         ▼                               │
                         │    dashboard-api (FastAPI)              │
                         │      │       │                          │
                         │      │       ▼                          │
                         │      │    MinIO (:9000)                 │
                         │      │    [state store PVC]             │
                         │      ▼                                  │
                         │    k8s API (RBAC)                       │
                         └──────┼──────────────────────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              friend-cyprien   friend-     (future friends)
              -iov namespace   abricot ns
```

---

## 4. Backend Architecture

### 4.1 Directory Structure

```
dashboard/api/
├── main.py                    # FastAPI app, lifespan, CORS
├── auth.py                    # BasicAuth verification (reads k8s Secrets)
├── config.py                  # Settings from env vars
├── database.py                # SQLite setup, migrations
├── models.py                  # Pydantic models
├── routers/
│   ├── friends.py             # CRUD + status
│   ├── state.py               # Save / restore / snapshots
│   └── health.py              # Liveness + readiness
├── services/
│   ├── k8s.py                 # Kubernetes API wrapper
│   ├── friend_manager.py      # Create / delete friend resources
│   ├── state_manager.py       # Tar-based backup/restore via k8s Jobs
│   └── minio_client.py        # MinIO upload/download
└── requirements.txt
```

### 4.2 API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/friends` | List all friends with status |
| `GET` | `/api/friends/{name}` | Get single friend details |
| `POST` | `/api/friends` | Create new friend (from template or new) |
| `DELETE` | `/api/friends/{name}` | Delete friend (teardown all resources) |
| `POST` | `/api/friends/{name}/state/save` | Trigger state backup to MinIO |
| `POST` | `/api/friends/{name}/state/restore` | Trigger state restore from MinIO |
| `GET` | `/api/friends/{name}/state` | List available snapshots |
| `GET` | `/api/health` | API health check |

---

## 5. Auth Model (Revised — No JWT)

The dashboard runs behind the same `hermes-basic` Traefik middleware that protects `hermes.caron.fun/`. This means:

- **No separate auth layer.** The browser prompts for basicAuth credentials before the dashboard loads at all.
- **No JWT tokens, no sessions, no cookies.** Traefik handles the 401 challenge.
- **Friend credentials** are read directly from k8s Secrets by the API (which already needs k8s access for management operations).
- **Destructive operations** (delete, save, restore) can optionally require re-entering the admin password (the same one used for the gateway).

**Rollback:** If the dashboard breaks, existing ttyd endpoints still work via direct URL + basicAuth. The dashboard is purely additive.

---

## 6. Storage Strategy (State Saving & Templating)

This is the critical feature. Given that `local-path` does NOT support VolumeSnapshots, we use a **tar-based approach** with Kubernetes Jobs.

### 6.1 What Gets Saved

Each friend's Hermes state consists of two paths inside the container:

| Path | Contents | Persistence |
|---|---|---|
| `/root/.hermes/` | `config.yaml`, `.env` (API keys), `cron/`, `sessions/`, `logs/` | **Ephemeral** — lost on pod restart unless saved |
| `/opt/data/` | User workspace files, any data stored outside `~/.hermes/` | **Persistent** — survives restart (PVC-mounted) |

The save Job tars **both paths** into a single archive. This captures everything: Hermes config, API keys, cron jobs, session history, and user workspace files.

### 6.2 Save State Flow

```
User clicks "Save State" on friend-alice
  │
  ▼
API creates Job in friend-alice namespace:
  ┌──────────────────────────────────────────────────┐
  │ apiVersion: batch/v1                             │
  │ kind: Job                                        │
  │ metadata:                                        │
  │   name: backup-<timestamp>                       │
  │   namespace: friend-alice                        │
  │ spec:                                            │
  │   template:                                      │
  │     spec:                                        │
  │       containers:                                │
  │         - name: backup                           │
  │           image: alpine:3.20                     │
  │           command: ["sh", "-c"]                  │
  │           args:                                  │
  │             - |                                  │
  │               apk add --no-cache minio-client && \
  │               tar czf /tmp/state.tar.gz \        │
  │                 -C /hermes-root .hermes \        │
  │                 -C /opt data &&                  │
  │               mc alias set local \               │
  │                 http://minio.dashboard:9000 \    │
  │                 $MINIO_ACCESS_KEY \              │
  │                 $MINIO_SECRET_KEY &&              │
  │               mc cp /tmp/state.tar.gz \          │
  │                 local/hermes-states/<key>        │
  │           volumeMounts:                          │
  │             - name: hermes-root                  │
  │               mountPath: /hermes-root            │
  │               readOnly: true                     │
  │             - name: data                         │
  │               mountPath: /opt/data               │
  │               readOnly: true                     │
  │           envFrom:                               │
  │             - secretRef:                         │
  │                 name: minio-credentials          │
  │       volumes:                                   │
  │         - name: hermes-root                      │
  │           emptyDir: {}                           │
  │         - name: data                             │
  │           persistentVolumeClaim:                 │
  │             claimName: friend-data               │
  │         - name: hermes-config                    │
  │           emptyDir: {}                           │
  └──────────────────────────────────────────────────┘
```

**Wait — the `/root/.hermes/` problem:** This path is inside the container filesystem (not PVC-mounted), so a separate Job can't directly access it. Two options:

**Option A (simplest):** The save script runs inside the *running* ttyd container via `kubectl exec`. It tars both paths and uploads to MinIO directly. The Job approach is only needed for restore.

**Option B:** Use a shared emptyDir or hostPath to pass `/root/.hermes/` to the backup container.

**Recommendation:** Option A. The save command runs as:
```bash
kubectl -n friend-alice exec deployment/ttyd -- \
  sh -c 'tar czf /tmp/state.tar.gz -C / .hermes opt/data && \
  apk add --no-cache minio-client && \
  mc cp /tmp/state.tar.gz local/hermes-states/<key>'
```

The restore command uses a Job that:
1. Downloads the tar from MinIO
2. Extracts `.hermes/` and `data/` into the PVC at `/opt/data/` and a shared volume
3. The next pod restart picks up the restored files

### 6.3 MinIO Object Layout

```
hermes-states/
├── cyprien-iov/
│   ├── backup-1751740000.tar.gz
│   └── backup-1751743600.tar.gz
├── abricot/
│   └── backup-1751740000.tar.gz
└── templates/
    ├── python-ml-env.tar.gz
    └── nodejs-fullstack.tar.gz
```

---

## 7. Container Lifecycle (How Create/Delete Works)

### 7.1 Create a New Friend

```
Admin clicks "Add Friend" → enters name + credentials
  │
  ▼
API (friend_manager.py) creates k8s resources:
  1. Namespace: friend-<name> (label traefik=enabled)
  2. ResourceQuota: 1Gi-2Gi mem, 4 CPU, 5 pods
  3. PVC: 2Gi local-path, claimName=friend-data
  4. Secret: friend-htpasswd (base64-encoded APR1 htpasswd)
  5. Middleware: friend-basic (basicAuth → friend-htpasswd)
  6. Deployment: ttyd (localhost/hermes-friends/ttyd:latest, Recreate, PVC mount /opt/data)
  7. Service: ttyd (ClusterIP :7681)
  8. IngressRoute: vanity (Host(`<name>.hermes.caron.fun`) → ttyd + TLS cfresolver)
  9. Update friends-registry ConfigMap → restart gateway
  │
  ▼
Friend accesses https://<name>.hermes.caron.fun/
  → 401 (basicAuth challenge)
  → enters <name>:<password>
  → ttyd web terminal loads
  → runs `hermes setup` interactively
```

**This mirrors add-friend.sh exactly.** Same resources, same naming, same Traefik wiring. The Python k8s client does what the shell script does.

### 7.2 Delete a Friend

```
Admin clicks "Delete" → confirms
  │
  ▼
API deletes namespace friend-<name> (cascading)
  → All resources inside are cleaned up automatically
  → Remove from friends-registry ConfigMap → restart gateway
```

### 7.3 View Status

```
Dashboard requests GET /api/friends
  │
  ▼
API queries k8s:
  - List all namespaces matching friend-*
  - For each: get Deployment status (pods, readiness, restarts)
  - For each: get PVC status (capacity, used)
  - For each: get IngressRoute (host, TLS status)
  │
  ▼
Returns JSON with friend list + real-time status
```

---

## 8. Frontend Architecture

### 8.1 Directory Structure

```
dashboard/frontend/
├── src/
│   ├── App.tsx               # Router setup
│   ├── components/
│   │   ├── layout/           # Header, sidebar, page wrapper
│   │   ├── friends/          # FriendList, FriendCard, FriendDetail
│   │   └── state/            # SnapshotList, SaveButton, RestoreButton
│   ├── hooks/                # useFriends, useStatus
│   ├── api/                  # API client (fetch wrapper)
│   └── types/                # TypeScript types matching backend models
├── index.html
├── vite.config.ts
├── tailwind.config.ts
└── package.json
```

### 8.2 Pages

| Page | Description |
|---|---|
| **Dashboard** (`/`) | Grid of friend cards: name, status badge (Running/Error/Stopped), pod uptime, storage used, action buttons |
| **Friend Detail** (`/friends/:name`) | Detailed view: container logs, resource usage, state snapshots, save/restore buttons, delete button |
| **New Friend** (`/friends/new`) | Form: name, username, password, template (optional), create button |

### 8.3 Key UI Components

- **FriendCard:** Shows name, status, uptime, subdomain link, quick actions
- **SnapshotList:** Lists available backups with timestamps, size, restore button
- **SaveButton:** Triggers state save, shows progress (polling Job status)
- **DeleteButton:** Requires confirmation dialog, shows cascading delete warning

---

## 9. Deployment Manifests (New Components)

### 9.1 Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: dashboard
  labels:
    traefik: enabled
```

### 9.2 RBAC

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dashboard-api
  namespace: dashboard
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dashboard-manager
rules:
  - apiGroups: [""]
    resources: ["namespaces", "services", "persistentvolumeclaims", "secrets", "configmaps", "pods", "resourcequotas"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["traefik.io"]
    resources: ["ingressroutes", "middlewares"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dashboard-manager
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: dashboard-manager
subjects:
  - kind: ServiceAccount
    name: dashboard-api
    namespace: dashboard
```

### 9.3 MinIO Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  namespace: dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
        - name: minio
          image: minio/minio:latest
          command: ["minio", "server", "/data", "--console-address", ":9001"]
          ports:
            - containerPort: 9000
            - containerPort: 9001
          envFrom:
            - secretRef:
                name: minio-credentials
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: 1
              memory: 512Mi
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: minio-data
---
apiVersion: v1
kind: Service
metadata:
  name: minio
  namespace: dashboard
spec:
  type: ClusterIP
  selector:
    app: minio
  ports:
    - name: api
      port: 9000
      targetPort: 9000
    - name: console
      port: 9001
      targetPort: 9001
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-data
  namespace: dashboard
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: Secret
metadata:
  name: minio-credentials
  namespace: dashboard
type: Opaque
stringData:
  MINIO_ROOT_USER: dashboard-admin
  MINIO_ROOT_PASSWORD: "CHANGE-ME-IN-PRODUCTION"
```

### 9.4 Dashboard API Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dashboard-api
  namespace: dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dashboard-api
  template:
    metadata:
      labels:
        app: dashboard-api
    spec:
      serviceAccountName: dashboard-api
      containers:
        - name: api
          image: localhost/hermes-friends/dashboard-api:latest
          ports:
            - containerPort: 8000
          env:
            - name: MINIO_ENDPOINT
              value: "http://minio:9000"
            - name: MINIO_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-credentials
                  key: MINIO_ROOT_USER
            - name: MINIO_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-credentials
                  key: MINIO_ROOT_PASSWORD
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: 1
              memory: 512Mi
```

### 9.5 Dashboard Frontend Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dashboard-frontend
  namespace: dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dashboard-frontend
  template:
    metadata:
      labels:
        app: dashboard-frontend
    spec:
      containers:
        - name: nginx
          image: nginx:1.27-alpine
          ports:
            - containerPort: 80
          volumeMounts:
            - name: html
              mountPath: /usr/share/nginx/html
              readOnly: true
            - name: nginx-conf
              mountPath: /etc/nginx/conf.d/default.conf
              readOnly: true
      volumes:
        - name: html
          configMap:
            name: dashboard-frontend-html
        - name: nginx-conf
          configMap:
            name: dashboard-frontend-nginx-conf
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: dashboard-frontend-nginx-conf
  namespace: dashboard
data:
  default.conf: |
    server {
        listen 80;
        root /usr/share/nginx/html;
        index index.html;

        location /api/ {
            proxy_pass http://dashboard-api:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location / {
            try_files $uri $uri/ /index.html;
        }
    }
```

### 9.6 IngressRoute (behind existing hermes-basic middleware)

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: dashboard
  namespace: dashboard
spec:
  entryPoints: [websecure]
  routes:
    - match: Host(`dashboard.hermes.caron.fun`)
      kind: Rule
      middlewares:
        - name: hermes-basic
          namespace: auth
      services:
        - name: dashboard-frontend
          port: 80
  tls:
    certResolver: cfresolver
```

---

## 10. Step-by-Step Implementation Plan

### Phase 1: Infrastructure (Day 1)
1. Add `dashboard.hermes.caron.fun` A record to Cloudflare (wildcard already covers it)
2. Create `dashboard` namespace + RBAC (ServiceAccount, ClusterRole, ClusterRoleBinding)
3. Deploy MinIO (Deployment + Service + PVC + credentials Secret)
4. Create `hermes-states` bucket in MinIO via `mc` client
5. Verify: MinIO console accessible at `minio:9001`

### Phase 2: Backend API (Days 2–3)
1. Implement FastAPI app skeleton with CORS, health endpoint
2. Implement `k8s.py` service (read/write k8s resources via Python client)
3. Implement `friend_manager.py` (create/delete — mirrors add-friend.sh logic)
4. Implement `state_manager.py` (tar-based backup via kubectl exec, restore via Job)
5. Implement `minio_client.py` (upload/download to hermes-states bucket)
6. Wire up all API routes, test with curl

### Phase 3: Frontend (Days 4–5)
1. Scaffold React + Vite + TailwindCSS project
2. Build API client layer (fetch wrapper)
3. Build Dashboard page (friend grid with status cards)
4. Build Friend Detail page (logs, snapshots, save/restore buttons)
5. Build New Friend form (name, username, password, template selector)

### Phase 4: Integration (Day 6)
1. End-to-end testing: create friend → verify ttyd works → save state → delete → restore from template
2. Add deployment manifests to repo
3. Write runbook for deploying dashboard on clean VM
4. Update README with dashboard section

---

## 11. Security Considerations

| Concern | Mitigation |
|---|---|
| **Dashboard is public** | Protected by `hermes-basic` Traefik middleware (same basicAuth as gateway). No separate auth layer needed |
| **k8s API access** | ServiceAccount with least-privilege ClusterRole. No access to kube-system |
| **MinIO credentials** | Stored in k8s Secret, mounted as env vars. Never in code or git |
| **PVC data** | MinIO data is PVC-backed. For production, use encrypted PVC or external S3 |
| **Container escape** | ttyd containers are unprivileged but run as root. Friends can `apt install` freely. Boundary is namespace isolation |
| **Rate limiting** | Add Traefik rate-limit middleware on dashboard IngressRoute if needed |

---

## 12. Estimated Resources

| Component | CPU | RAM | Storage |
|---|---|---|---|
| dashboard-api | 200m–1 | 256Mi–512Mi | 1Gi (SQLite) |
| dashboard-frontend | 50m–200m | 32Mi–64Mi | — |
| minio | 250m–1 | 256Mi–512Mi | 10Gi (state store) |
| **Total overhead** | **~500m** | **~512Mi–1Gi** | **~11Gi** |

Current usage: 1.3/8 cores (16%), 3.3/8Gi (41%). After dashboard: ~1.8/8 cores (22%), ~4.3/8Gi (54%). Plenty of headroom.
