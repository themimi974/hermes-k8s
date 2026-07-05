# hermes-k8s Dashboard — Architecture Design

**Author:** Hermes Agent (auto-generated from live cluster analysis)  
**Date:** 2026-07-05  
**Status:** Design — not yet implemented

---

## 1. Current State Summary

| What | Where | Real values |
|---|---|---|
| k3s node | host-005 | 192.168.1.174, 8 cores, 8Gi RAM |
| Traefik | kube-system | IngressRouteCRDs, cfresolver (Cloudflare DNS-01) |
| StorageClass | `local-path` | rancher.io/local-path, **no VolumeSnapshot support** |
| Friends | friend-cyprien-iov, friend-abricot | 2Gi PVC each, ttyd pods |
| Gateway | auth/hermes-gateway-vanity | nginx landing page at hermes.caron.fun |
| Auth | htpasswd per-friend + hermes-basic | BasicAuth Traefik Middlewares |

**Key constraint:** `local-path` StorageClass does not support VolumeSnapshots. All state save/restore must use a tar-based approach (Job that mounts PVC, tars contents, uploads to object storage).

**Current resource usage:** 33% CPU (1.3/4 cores), 41% RAM (3.3/8Gi). Headroom exists for dashboard infra (~200Mi backend + 50Mi frontend + MinIO 256Mi).

---

## 2. Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend** | React + Vite + TailwindCSS + shadcn/ui | Fast iteration, great DX, component library free |
| **Backend API** | Python 3.11+ FastAPI | Native async, `kubernetes` Python client, OpenAPI docs auto-generated |
| **Database** | SQLite (POC) → PostgreSQL (prod) | Zero-config for POC; easy migration later |
| **Object Storage** | MinIO (in-cluster) | S3-compatible, single binary, runs as Deployment + PVC |
| **Auth** | JWT (bcrypt passwords + access/refresh tokens) | Simple, upgradeable to OIDC later |
| **Image Registry** | Existing podman → k3s containerd flow | No change to current image pipeline |
| **Reverse Proxy** | Existing Traefik | Dashboard gets its own IngressRoute in `dashboard` namespace |

**Why not alternatives:**
- *Go + client-go:* Faster runtime but slower iteration for POC. Python `kubernetes` client is mature enough.
- *Next.js:* Overkill for a dashboard. React SPA served by nginx is simpler.
- *Keycloak/OIDC:* Adds 500Mi+ RAM and complexity. JWT is sufficient for this scale.
- *PostgreSQL:* Extra PVC + StatefulSet for a 2-user POC. SQLite embedded in the API container.
- *Velero:* Requires restic + minio anyway, and doesn't work well with local-path. Custom tar approach is simpler and more transparent.

---

## 3. Component Diagram

```
                         ┌─────────────────────────────────────────┐
                         │            dashboard namespace          │
                         │                                         │
Internet ──HTTPS──► Traefik ──► dashboard-frontend (nginx)        │
                                     │ serves React SPA            │
                                     │                             │
                         ┌───────────┤                             │
                         │           │                             │
                    /api/*     /ws/* (future)                      │
                         │           │                             │
                         ▼           │                             │
                   dashboard-api     │                             │
                   (FastAPI)         │                             │
                   ├── SQLite PVC ───┤                             │
                   ├── MinIO client──┼──────► minio (Deployment)  │
                   │                 │         ├── data PVC        │
                   │                 │         └── S3 API :9000    │
                   │                 │                             │
                   └── k8s client────┼──► kube-apiserver          │
                                     │                             │
                         └───────────┴─────────────────────────────┘

    Per-friend namespaces (existing, managed by API):
    ├── friend-alice/
    │   ├── Deployment ttyd
    │   ├── Service ttyd:7681
    │   ├── IngressRoute vanity
    │   ├── Middleware friend-basic
    │   ├── Secret friend-htpasswd
    │   └── PVC friend-data (2Gi)
    └── friend-bob/
        └── (same structure)
```

### New components to deploy:

| Component | Image | Namespace | Resources | PVC |
|---|---|---|---|---|
| `dashboard-api` | `hermes-dashboard-api:latest` (custom build) | `dashboard` | 200m–1 CPU, 256Mi–512Mi | 1Gi (SQLite) |
| `dashboard-frontend` | `nginx:1.27-alpine` + static build | `dashboard` | 50m–200m CPU, 32Mi–64Mi | none |
| `minio` | `minio/minio:latest` | `dashboard` | 250m–1 CPU, 256Mi–512Mi | 10Gi (state store) |

**Total overhead:** ~500Mi RAM, ~0.5 CPU cores — well within the node's headroom (8Gi/8 cores, currently 41% used).

---

## 4. Backend Architecture

### 4.1 API Design

```
POST   /api/auth/login              → { access_token, refresh_token }
POST   /api/auth/refresh            → { access_token }

GET    /api/users                   → list all users
POST   /api/users                   → create user { username, password, role }
GET    /api/users/{id}              → user details + their containers
PUT    /api/users/{id}              → update user { password, role }
DELETE /api/users/{id}              → nuke user (cascade delete all k8s resources)

GET    /api/containers              → list containers (admin: all, user: own)
POST   /api/containers              → create container { name, template_id? }
DELETE /api/containers/{id}         → delete container + PVC + namespace

POST   /api/containers/{id}/save    → save PVC state → { backup_id }
GET    /api/containers/{id}/backups → list backups for this container
POST   /api/containers/{id}/restore → restore from backup { backup_id }

GET    /api/templates               → list user's templates
POST   /api/templates               → create template { name, source_container_id }
DELETE /api/templates/{id}          → delete template + its data from MinIO
POST   /api/templates/{id}/deploy   → deploy new container from template
```

### 4.2 RBAC Model

Two roles, enforced via FastAPI dependency injection:

| Role | Permissions |
|---|---|
| `admin` | All endpoints. Manage users. Delete any container. Nuke users. |
| `user` | CRUD own containers. Save/restore own PVC state. Manage own templates. Cannot touch other users' resources. |

### 4.3 k8s Client Configuration

```python
# dashboard-api/config.py
from kubernetes import config, client

# In-cluster (running as a Pod with ServiceAccount)
config.load_incluster_config()
k8s = client.ApiClient()

# For local dev: config.load_kube_config()
```

The API pod gets a **dedicated ServiceAccount** with a **Role** scoped to:
- `list`, `get`, `create`, `delete` on: `namespaces`, `deployments`, `services`, `ingressroutes.traefik.io`, `middlewares.traefik.io`, `secrets`, `persistentvolumeclaims`, `jobs`, `pods`
- **No** `update` on existing namespaces (prevents tampering)
- **No** access to `kube-system` or other system namespaces

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
    resources: ["namespaces", "services", "secrets", "persistentvolumeclaims", "pods", "jobs"]
    verbs: ["get", "list", "create", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "create", "delete"]
  - apiGroups: ["traefik.io"]
    resources: ["ingressroutes", "middlewares"]
    verbs: ["get", "list", "create", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dashboard-manager
subjects:
  - kind: ServiceAccount
    name: dashboard-api
    namespace: dashboard
roleRef:
  kind: ClusterRole
  name: dashboard-manager
  apiGroup: rbac.authorization.k8s.io
```

---

## 5. State Management (Database Schema)

### 5.1 SQLite Schema

```sql
-- Users table (replaces htpasswd)
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,  -- bcrypt hash
    role        TEXT NOT NULL CHECK(role IN ('admin', 'user')),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Containers table (maps to k8s namespace + resources)
CREATE TABLE containers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    namespace   TEXT NOT NULL,  -- friend-<name>
    subdomain   TEXT NOT NULL,  -- <name>.hermes.caron.fun
    status      TEXT DEFAULT 'running',  -- running, stopped, error
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

-- Backups (PVC snapshots stored in MinIO)
CREATE TABLE backups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id INTEGER NOT NULL REFERENCES containers(id) ON DELETE CASCADE,
    type        TEXT NOT NULL CHECK(type IN ('backup', 'template')),
    name        TEXT,  -- NULL for backups, template name for templates
    object_key  TEXT NOT NULL,  -- MinIO path: backups/{user_id}/{container_id}/{id}.tar.gz
    size_bytes  INTEGER,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Sessions (JWT refresh tokens)
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token TEXT UNIQUE NOT NULL,
    expires_at  DATETIME NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 Auth Flow

```
User → POST /api/auth/login { username, password }
  → API verifies bcrypt hash against users table
  → Returns JWT access_token (15min) + refresh_token (7 days)

User → Any /api/* request with Authorization: Bearer <access_token>
  → FastAPI dependency decodes JWT, loads user from DB
  → RBAC check: admin sees all, user sees own resources

User → POST /api/auth/refresh { refresh_token }
  → Verifies token not expired, not revoked
  → Returns new access_token
```

---

## 6. Storage Strategy (State Saving & Templating)

This is the critical feature. Given that `local-path` does NOT support VolumeSnapshots, we use a **tar-based approach** with Kubernetes Jobs.

### 6.1 Save State Flow

```
User clicks "Save State" on container alice-data
  │
  ▼
API creates Job in friend-alice namespace:
  ┌──────────────────────────────────────────────┐
  │ apiVersion: batch/v1                         │
  │ kind: Job                                    │
  │ metadata:                                    │
  │   name: backup-<timestamp>                   │
  │   namespace: friend-alice                    │
  │ spec:                                        │
  │   template:                                  │
  │     spec:                                    │
  │       containers:                            │
  │         - name: backup                       │
  │           image: alpine:3.20                 │
  │           command: ["sh", "-c"]              │
  │           args:                              │
  │             - |                              │
  │               tar czf /tmp/state.tar.gz -C /data . && \
  │               apk add --no-cache minio-client && \
  │               mc alias set local http://minio.dashboard:9000 KEY SECRET && \
  │               mc cp /tmp/state.tar.gz local/hermes-states/<key>
  │           volumeMounts:                      │
  │             - name: data                     │
  │               mountPath: /data               │
  │       volumes:                               │
  │         - name: data                         │
  │           persistentVolumeClaim:             │
  │             claimName: friend-data           │
  └──────────────────────────────────────────────┘
  │
  ▼
API polls Job status (watch or poll every 5s)
  │
  ▼
Job completes → API records backup in SQLite with MinIO object_key
  │
  ▼
API deletes the backup Job (cleanup)
```

### 6.2 MinIO Object Layout

```
hermes-states/
├── 1/                          # user_id
│   ├── alice/                  # container_name
│   │   ├── backup-1720200000.tar.gz    # timestamped backup
│   │   └── backup-1720203600.tar.gz
│   └── templates/
│       ├── my-dev-env.tar.gz           # named template
│       └── python-ml-setup.tar.gz
└── 2/
    └── bob/
        └── ...
```

### 6.3 Deploy from Template Flow

```
User picks template "my-dev-env" and clicks "Deploy"
  │
  ▼
API creates new PVC (2Gi) in new namespace friend-<new-name>
  │
  ▼
API creates restore Job:
  ┌──────────────────────────────────────────────┐
  │ Job that:                                    │
  │ 1. Downloads template tar from MinIO         │
  │ 2. Extracts to /data (mounted new PVC)       │
  └──────────────────────────────────────────────┘
  │
  ▼
Job completes → API creates ttyd Deployment + Service + IR + MW + Secret
  │
  ▼
Container is live at <new-name>.hermes.caron.fun with pre-populated state
```

### 6.4 PVC Cloning (Advanced — Not POC)

For large PVCs (10Gi+), the tar approach is slow. A faster alternative:

1. **CSI clone:** If using a CSI driver that supports cloning (Longhorn, OpenEBS), clone the PVC directly. Not available with `local-path`.
2. **Stash/Velero:** Use Stash (for PVC snapshots via restic) or Velero (for backup + restore). Both require their own infrastructure.
3. **Pre-built images:** Bake the state into a custom Docker image. Fastest deployment but inflexible.

**Recommendation:** Start with tar-based (works with any StorageClass). Optimize later if PVCs grow beyond 5Gi.

---

## 7. Container Lifecycle (How Create/Delete Works)

### 7.1 Create Container

When a user clicks "New Container":

```
API:
1. Generate unique name: user-<random4> (e.g., user-xk7f)
2. Create namespace: friend-<name> with label traefik=enabled
3. Create ResourceQuota (1Gi-2Gi mem, 4 CPU, 5 pods)
4. Create PVC friend-data (2Gi, local-path)
5. Create Secret friend-htpasswd (bcrypt of user's password)
6. Create Middleware friend-basic (basicAuth → friend-htpasswd)
7. Create Deployment ttyd (localhost/hermes-friends/ttyd:latest, Recreate)
8. Create Service ttyd (ClusterIP :7681)
9. Create IngressRoute vanity (Host(<name>.hermes.caron.fun) → ttyd + TLS)
10. Update friends-registry ConfigMap + restart gateway
11. Record in SQLite containers table
```

This is exactly what `add-friend.sh` does today, just programmatically via the k8s Python client.

### 7.2 Delete Container (Single)

```
API:
1. Delete namespace friend-<name> (cascading: all resources)
2. Delete backup Jobs if any (cleanup)
3. Update friends-registry ConfigMap + restart gateway
4. Mark container as 'deleted' in SQLite (or remove row)
```

### 7.3 Nuke User

```
Admin clicks "Delete User" on user with 3 containers:
1. For each container: delete namespace (cascade)
2. For each backup/template in MinIO: delete objects
3. Delete user from SQLite (cascades to containers + backups + sessions)
4. Update gateway registry
```

---

## 8. Frontend Architecture

### 8.1 Pages

| Route | Component | Auth | Description |
|---|---|---|---|
| `/login` | LoginPage | none | Username + password form |
| `/` | Dashboard | any | Overview: list of user's containers with status |
| `/containers/new` | NewContainer | any | Form: name, pick template (optional) |
| `/containers/:id` | ContainerDetail | owner | Status, open shell link, save/restore buttons |
| `/templates` | Templates | any | List templates, create from container, delete |
| `/admin/users` | UserManagement | admin | CRUD users, view their containers |
| `/admin/containers` | AllContainers | admin | All containers across all users |

### 8.2 Component Structure

```
src/
├── components/
│   ├── ui/              # shadcn/ui primitives (Button, Card, Dialog, etc.)
│   ├── layout/          # Sidebar, Header, ProtectedRoute
│   ├── containers/      # ContainerCard, ContainerList, NewContainerForm
│   ├── templates/       # TemplateCard, SaveTemplateDialog
│   └── admin/           # UserTable, UserForm, NukeDialog
├── pages/
│   ├── Login.tsx
│   ├── Dashboard.tsx
│   ├── ContainerDetail.tsx
│   ├── Templates.tsx
│   └── admin/
│       ├── Users.tsx
│       └── AllContainers.tsx
├── api/                 # Axios/fetch wrapper with JWT interceptor
│   └── client.ts
├── hooks/               # useAuth, useContainers, useTemplates
└── lib/                 # utils, types
```

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

### 9.2 SQLite PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: dashboard-db
  namespace: dashboard
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 1Gi
```

### 9.3 MinIO

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  namespace: dashboard
spec:
  replicas: 1
  selector:
    matchLabels: { app: minio }
  template:
    metadata:
      labels: { app: minio }
    spec:
      containers:
        - name: minio
          image: minio/minio:latest
          command: ["minio", "server", "/data", "--console-address", ":9001"]
          env:
            - name: MINIO_ROOT_USER
              valueFrom:
                secretKeyRef: { name: minio-credentials, key: root-user }
            - name: MINIO_ROOT_PASSWORD
              valueFrom:
                secretKeyRef: { name: minio-credentials, key: root-password }
          ports: [{ containerPort: 9000 }, { containerPort: 9001 }]
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests: { cpu: 250m, memory: 256Mi }
            limits: { cpu: 1, memory: 512Mi }
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
  selector: { app: minio }
  ports:
    - name: api
      port: 9000
    - name: console
      port: 9001
```

### 9.4 Dashboard API

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dashboard-api
  namespace: dashboard
spec:
  replicas: 1
  selector:
    matchLabels: { app: dashboard-api }
  template:
    metadata:
      labels: { app: dashboard-api }
    spec:
      serviceAccountName: dashboard-api
      containers:
        - name: api
          image: hermes-dashboard-api:latest
          ports: [{ containerPort: 8000 }]
          env:
            - name: DATABASE_URL
              value: "sqlite:///data/dashboard.db"
            - name: MINIO_ENDPOINT
              value: "minio:9000"
            - name: MINIO_ACCESS_KEY
              valueFrom:
                secretKeyRef: { name: minio-credentials, key: root-user }
            - name: MINIO_SECRET_KEY
              valueFrom:
                secretKeyRef: { name: minio-credentials, key: root-password }
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef: { name: jwt-secret, key: key }
            - name: DOMAIN
              value: "hermes.caron.fun"
          volumeMounts:
            - name: db
              mountPath: /data
          resources:
            requests: { cpu: 200m, memory: 256Mi }
            limits: { cpu: 1, memory: 512Mi }
      volumes:
        - name: db
          persistentVolumeClaim:
            claimName: dashboard-db
```

### 9.5 Dashboard Frontend

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dashboard-frontend
  namespace: dashboard
spec:
  replicas: 1
  selector:
    matchLabels: { app: dashboard-frontend }
  template:
    metadata:
      labels: { app: dashboard-frontend }
    spec:
      containers:
        - name: nginx
          image: hermes-dashboard-frontend:latest
          ports: [{ containerPort: 80 }]
          resources:
            requests: { cpu: 50m, memory: 32Mi }
            limits: { cpu: 200m, memory: 64Mi }
---
apiVersion: v1
kind: Service
metadata:
  name: dashboard-frontend
  namespace: dashboard
spec:
  selector: { app: dashboard-frontend }
  ports: [{ port: 80, targetPort: 80 }]
```

### 9.6 IngressRoute (dashboard.hermes.caron.fun)

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: dashboard-vanity
  namespace: dashboard
spec:
  entryPoints: [websecure]
  routes:
    - match: Host(`dashboard.hermes.caron.fun`)
      kind: Rule
      services:
        - name: dashboard-frontend
          port: 80
    - match: Host(`dashboard.hermes.caron.fun`) && PathPrefix(`/api`)
      kind: Rule
      services:
        - name: dashboard-api
          port: 8000
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

### Phase 2: Backend API (Days 2–3)
1. Scaffold FastAPI project with Dockerfile
2. Implement SQLite schema + migrations (Alembic)
3. Implement auth endpoints (login, refresh, bcrypt)
4. Implement user CRUD (admin-only)
5. Implement container CRUD (k8s client calls — mirror add-friend.sh logic exactly)
6. Implement state save (Job creation + MinIO upload)
7. Implement state restore (Job creation + MinIO download)
8. Implement template CRUD
9. Write tests (pytest + k3s test cluster)

### Phase 3: Frontend (Days 4–5)
1. Scaffold React + Vite + TailwindCSS + shadcn/ui
2. Build login page + JWT auth flow
3. Build container list + detail pages
4. Build new container form (with template picker)
5. Build save/restore UI (progress indicators for Jobs)
6. Build template management page
7. Build admin user management page
8. Build admin container overview page

### Phase 4: Integration + Polish (Day 6)
1. Deploy frontend + API to cluster
2. Test full flow: login → create container → open shell → save → delete → restore from template
3. Update README.md with dashboard deployment instructions
4. Write runbook for common operations

---

## 11. Migration Path (htpasswd → Dashboard DB)

During the transition, both auth mechanisms coexist:

1. **Phase 1:** Dashboard API is deployed alongside existing htpasswd auth
2. **Phase 2:** First admin user is created in SQLite (via CLI seed command)
3. **Phase 3:** Dashboard IngressRoute gets **no basicAuth middleware** — auth is handled by JWT at the API level
4. **Phase 4:** Existing friend-htpasswd Secrets remain for backward compatibility (users can still access ttyd directly)
5. **Phase 5 (optional):** Remove Traefik basicAuth middlewares from friend IngressRoutes — all access goes through dashboard

**Rollback:** If dashboard breaks, existing ttyd endpoints still work via direct URL + basicAuth.

---

## 12. Security Considerations

| Concern | Mitigation |
|---|---|
| **Dashboard is public** | JWT auth required. Add Cloudflare Access or a simple IP allowlist in Traefik if needed |
| **k8s API access** | ServiceAccount with least-privilege ClusterRole. No access to kube-system |
| **MinIO credentials** | Stored in k8s Secret, mounted as env vars. Never in code or git |
| **JWT secret** | Generated random 256-bit key, stored in k8s Secret |
| **PVC data** | MinIO data is PVC-backed. For production, use encrypted PVC or external S3 |
| **Container escape** | ttyd containers are unprivileged but run as root. Friends can `apt install` freely. Boundary is namespace isolation |
| **Rate limiting** | Add Traefik rate-limit middleware on dashboard IngressRoute to prevent abuse |

---

## 13. Estimated Resources

| Component | CPU | RAM | Storage | Cost impact |
|---|---|---|---|---|
| dashboard-api | 200m–1 | 256Mi–512Mi | 1Gi (SQLite) | Low |
| dashboard-frontend | 50m–200m | 32Mi–64Mi | — | Minimal |
| minio | 250m–1 | 256Mi–512Mi | 10Gi (state store) | Low |
| **Total overhead** | **~500m** | **~512Mi–1Gi** | **~11Gi** | **Well within 8-core/8Gi node** |

Current usage: 1.3/8 cores (16%), 3.3/8Gi (41%). After dashboard: ~1.8/8 cores (22%), ~4.3/8Gi (54%). Plenty of headroom.
