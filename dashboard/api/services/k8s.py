"""Kubernetes API wrapper using in-cluster config."""
from __future__ import annotations

import logging
from typing import Optional

from kubernetes import client, config as k8s_config

from config import settings

logger = logging.getLogger(__name__)

# Load config once at module level
try:
    k8s_config.load_incluster_config()
    logger.info("Loaded in-cluster Kubernetes config")
except k8s_config.ConfigException:
    logger.warning("In-cluster config failed, falling back to kubeconfig")
    k8s_config.load_kube_config()

# API clients
v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
batch_v1 = client.BatchV1Api()
custom_api = client.CustomObjectsApi()
exec_api = client.api_client.ApiClient()


def list_friend_namespaces() -> list[str]:
    """List all namespaces matching friend-* pattern."""
    ns_list = v1.list_namespace(label_selector="traefik=enabled")
    return [ns.metadata.name for ns in ns_list.items if ns.metadata.name.startswith("friend-")]


def get_namespace(ns: str) -> Optional[client.V1Namespace]:
    """Get a specific namespace by name."""
    try:
        return v1.read_namespace(ns)
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return None
        raise


def create_namespace(ns: str) -> client.V1Namespace:
    """Create a namespace with traefik label."""
    body = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=ns,
            labels={"traefik": "enabled"},
        )
    )
    return v1.create_namespace(body=body)


def delete_namespace(ns: str) -> None:
    """Delete a namespace (cascading)."""
    try:
        v1.delete_namespace(name=ns, body=client.V1DeleteOptions(propagation_policy="Foreground"))
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return
        raise


def get_deployment_status(ns: str, name: str = "ttyd") -> dict:
    """Get deployment status: pods, ready_pods, restarts."""
    result = {"pods": 0, "ready_pods": 0, "restarts": 0, "status": "not-found"}
    try:
        dep = apps_v1.read_namespaced_deployment(name=name, namespace=ns)
        # Get associated replicasets
        rs_list = apps_v1.list_namespaced_replica_set(
            namespace=ns,
            label_selector=",".join(
                f"{k}={v}" for k, v in dep.spec.selector.match_labels.items()
            ),
        )
        for rs in rs_list.items:
            if rs.status.ready_replicas:
                result["ready_pods"] = rs.status.ready_replicas
            result["pods"] = rs.status.replicas or 0

        # Get pod restart counts
        pods = v1.list_namespaced_pod(
            namespace=ns,
            label_selector=",".join(
                f"{k}={v}" for k, v in dep.spec.selector.match_labels.items()
            ),
        )
        total_restarts = 0
        for pod in pods.items:
            if pod.status and pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    total_restarts += cs.restart_count
        result["restarts"] = total_restarts

        # Determine overall status
        if dep.status and dep.status.available_replicas:
            result["status"] = "running"
        elif dep.status and dep.status.unavailable_replicas:
            result["status"] = "pending"
        else:
            result["status"] = "unknown"
    except client.exceptions.ApiException as e:
        if e.status != 404:
            logger.error(f"Error getting deployment status for {ns}/{name}: {e}")
        result["status"] = "not-found"
    return result


def get_pvc_status(ns: str, name: str = "friend-data") -> dict:
    """Get PVC status."""
    result = {"name": name, "status": "Unknown", "size": settings.friend_storage_size}
    try:
        pvc = v1.read_namespaced_persistent_volume_claim(name=name, namespace=ns)
        result["status"] = pvc.status.phase if pvc.status else "Unknown"
        if pvc.spec.resources.requests and "storage" in pvc.spec.resources.requests:
            result["size"] = str(pvc.spec.resources.requests["storage"])
    except client.exceptions.ApiException as e:
        if e.status != 404:
            logger.error(f"Error getting PVC status for {ns}/{name}: {e}")
    return result


def get_ingressroute_host(ns: str) -> Optional[str]:
    """Get the host from the first IngressRoute in the namespace."""
    try:
        irs = custom_api.list_namespaced_custom_object(
            group="traefik.io",
            version="v1alpha1",
            namespace=ns,
            plural="ingressroutes",
        )
        for ir in irs.get("items", []):
            spec = ir.get("spec", {})
            routes = spec.get("routes", [])
            for route in routes:
                match = route.get("match", "")
                if "Host(" in match:
                    # Extract host from Host(`xxx.hermes.caron.fun`)
                    import re
                    m = re.search(r"Host\(`([^`]+)`\)", match)
                    if m:
                        return m.group(1)
    except Exception as e:
        logger.warning(f"Error getting IngressRoute for {ns}: {e}")
    return None


def create_resource_quota(ns: str) -> None:
    """Create ResourceQuota for the friend namespace."""
    body = {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {"name": "friend-quota", "namespace": ns},
        "spec": {
            "hard": {
                "requests.cpu": "1",
                "requests.memory": "512Mi",
                "limits.cpu": "2",
                "limits.memory": "1Gi",
                "persistentvolumeclaims": "1",
            }
        },
    }
    try:
        v1.create_namespaced_resource_quota(namespace=ns, body=body)
    except client.exceptions.ApiException as e:
        if e.status != 409:  # Already exists
            raise


def create_pvc(ns: str) -> None:
    """Create PVC for friend data."""
    body = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(name="friend-data", namespace=ns),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            storage_class_name=settings.friend_storage_class,
            resources=client.V1VolumeResourceRequirements(
                requests={"storage": settings.friend_storage_size}
            ),
        ),
    )
    try:
        v1.create_namespaced_persistent_volume_claim(namespace=ns, body=body)
    except client.exceptions.ApiException as e:
        if e.status != 409:
            raise


def create_htpasswd_secret(ns: str, username: str, password_b64: str) -> None:
    """Create the friend-htpasswd secret with base64-encoded users."""
    body = client.V1Secret(
        metadata=client.V1ObjectMeta(name="friend-htpasswd", namespace=ns),
        type="Opaque",
        data={"users": password_b64},
    )
    try:
        v1.create_namespaced_secret(namespace=ns, body=body)
    except client.exceptions.ApiException as e:
        if e.status != 409:
            raise


def create_middleware(ns: str) -> None:
    """Create Traefik basicAuth middleware."""
    body = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "Middleware",
        "metadata": {"name": "friend-basic", "namespace": ns},
        "spec": {
            "basicAuth": {
                "secret": "friend-htpasswd",
            }
        },
    }
    try:
        custom_api.create_namespaced_custom_object(
            group="traefik.io",
            version="v1alpha1",
            namespace=ns,
            plural="middlewares",
            body=body,
        )
    except Exception as e:
        if "already exists" not in str(e).lower() and "409" not in str(e):
            raise


def create_deployment(ns: str) -> None:
    """Create the ttyd deployment."""
    labels = {"app": "ttyd", "friend": ns.replace("friend-", "")}
    body = client.V1Deployment(
        metadata=client.V1ObjectMeta(name="ttyd", namespace=ns, labels=labels),
        spec=client.V1DeploymentSpec(
            replicas=1,
            strategy=client.V1DeploymentStrategy(type="Recreate"),
            selector=client.V1LabelSelector(match_labels=labels),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="ttyd",
                            image=settings.friend_image,
                            image_pull_policy="Never",
                            ports=[client.V1ContainerPort(container_port=7681)],
                            readiness_probe=client.V1Probe(
                                tcp_socket=client.V1TCPSocketAction(port=7681),
                                initial_delay_seconds=5,
                                period_seconds=10,
                            ),
                            liveness_probe=client.V1Probe(
                                tcp_socket=client.V1TCPSocketAction(port=7681),
                                initial_delay_seconds=30,
                                period_seconds=30,
                            ),
                            resources=client.V1ResourceRequirements(
                                requests={
                                    "cpu": settings.friend_cpu_request,
                                    "memory": settings.friend_memory_request,
                                },
                                limits={
                                    "cpu": settings.friend_cpu_limit,
                                    "memory": settings.friend_memory_limit,
                                },
                            ),
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="friends-data",
                                    mount_path="/opt/data",
                                )
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="friends-data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name="friend-data",
                            ),
                        )
                    ],
                ),
            ),
        ),
    )
    try:
        apps_v1.create_namespaced_deployment(namespace=ns, body=body)
    except client.exceptions.ApiException as e:
        if e.status != 409:
            raise


def create_service(ns: str) -> None:
    """Create the ttyd ClusterIP service."""
    labels = {"app": "ttyd", "friend": ns.replace("friend-", "")}
    body = client.V1Service(
        metadata=client.V1ObjectMeta(name="ttyd", namespace=ns, labels=labels),
        spec=client.V1ServiceSpec(
            type="ClusterIP",
            selector=labels,
            ports=[
                client.V1ServicePort(name="ttyd", port=7681, target_port=7681)
            ],
        ),
    )
    try:
        v1.create_namespaced_service(namespace=ns, body=body)
    except client.exceptions.ApiException as e:
        if e.status != 409:
            raise


def create_ingressroute(ns: str, host: str) -> None:
    """Create Traefik IngressRoute — adapts to TLS method."""
    tls_method = settings.tls_method

    # Build TLS block based on method
    if tls_method == "http":
        entry_points = ["web"]
        tls_block = None
    else:
        entry_points = ["websecure"]
        if tls_method == "selfsigned":
            tls_block = {"secretName": "hermes-tls"}
        else:  # letsencrypt
            tls_block = {"certResolver": settings.tls_cert_resolver}

    body = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "IngressRoute",
        "metadata": {"name": "vanity", "namespace": ns},
        "spec": {
            "entryPoints": entry_points,
            "routes": [
                {
                    "match": f"Host(`{host}`)",
                    "kind": "Rule",
                    "services": [
                        {"name": "ttyd", "port": 7681}
                    ],
                }
            ],
        },
    }
    if tls_block:
        body["spec"]["tls"] = tls_block

    try:
        custom_api.create_namespaced_custom_object(
            group="traefik.io",
            version="v1alpha1",
            namespace=ns,
            plural="ingressroutes",
            body=body,
        )
    except Exception as e:
        if "already exists" not in str(e).lower() and "409" not in str(e):
            raise


def create_restore_job(ns: str, snapshot_key: str, image: str = "alpine:3.20") -> str:
    """Create a Job to restore state from MinIO snapshot into PVC."""
    import uuid
    job_name = f"restore-{uuid.uuid4().hex[:8]}"
    body = client.V1Job(
        metadata=client.V1ObjectMeta(name=job_name, namespace=ns),
        spec=client.V1JobSpec(
            backoff_limit=1,
            template=client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="restore",
                            image=image,
                            command=["sh", "-c"],
                            args=[
                                "apk add --no-cache minio-client && "
                                f"mc alias set local http://minio.dashboard:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY && "
                                f"mc cp local/{snapshot_key} /tmp/state.tar.gz && "
                                "tar xzf /tmp/state.tar.gz -C /mnt --strip-components=0 || "
                                "tar xzf /tmp/state.tar.gz -C /mnt"
                            ],
                            env=[
                                client.V1EnvVar(name="MINIO_ACCESS_KEY", value=settings.minio_access_key),
                                client.V1EnvVar(name="MINIO_SECRET_KEY", value=settings.minio_secret_key),
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="data",
                                    mount_path="/mnt",
                                )
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name="friend-data",
                            ),
                        )
                    ],
                ),
            ),
        ),
    )
    batch_v1.create_namespaced_job(namespace=ns, body=body)
    return job_name


def get_running_pods(ns: str, label_selector: str = "app=ttyd") -> list[str]:
    """Get running pod names in a namespace."""
    pods = v1.list_namespaced_pod(
        namespace=ns,
        label_selector=label_selector,
        field_selector="status.phase=Running",
    )
    return [pod.metadata.name for pod in pods.items]
