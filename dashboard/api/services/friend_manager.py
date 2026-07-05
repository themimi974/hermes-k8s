"""Friend management service — creates/deletes k8s resources."""
from __future__ import annotations

import base64
import logging
from typing import Optional

from passlib.hash import apr_md5_crypt

from config import settings
from models import FriendInfo, FriendDetail
from services import k8s

logger = logging.getLogger(__name__)


def generate_htpasswd_b64(username: str, password: str) -> str:
    """Generate APR1/MD5 htpasswd entry, base64-encoded for k8s Secret."""
    h = apr_md5_crypt.using(salt_size=8).hash(password)
    entry = f"{username}:{h}\n"
    return base64.b64encode(entry.encode()).decode()


def get_friend_info(name: str) -> Optional[FriendDetail]:
    """Get detailed info for a single friend."""
    ns = f"friend-{name}"
    namespace = k8s.get_namespace(ns)
    if namespace is None:
        return None

    dep_status = k8s.get_deployment_status(ns)
    pvc = k8s.get_pvc_status(ns)
    host = k8s.get_ingressroute_host(ns)

    # Try to get username from k8s secret
    username = None
    try:
        secret = k8s.v1.read_namespaced_secret(name="friend-htpasswd", namespace=ns)
        if secret.data and "users" in secret.data:
            decoded = base64.b64decode(secret.data["users"]).decode()
            username = decoded.split(":")[0]
    except Exception:
        pass

    return FriendDetail(
        name=name,
        namespace=ns,
        status=dep_status["status"],
        host=host,
        pods=dep_status["pods"],
        ready_pods=dep_status["ready_pods"],
        restarts=dep_status["restarts"],
        pvc_name=pvc["name"],
        pvc_status=pvc["status"],
        pvc_size=pvc["size"],
        ingressroute_host=host,
        username=username,
    )


def list_friends() -> list[FriendInfo]:
    """List all friends with their status."""
    namespaces = k8s.list_friend_namespaces()
    friends = []
    for ns in namespaces:
        name = ns.replace("friend-", "")
        info = get_friend_info(name)
        if info:
            friends.append(info)
    return friends


def create_friend(name: str, username: str, password: str) -> FriendDetail:
    """Create a new friend — mirrors add-friend.sh logic."""
    ns = f"friend-{name}"
    host = f"{name}.{settings.friend_domain}"

    logger.info(f"Creating friend {name} (namespace: {ns})")

    # 1. Namespace
    k8s.create_namespace(ns)
    logger.info(f"  Created namespace {ns}")

    # 2. ResourceQuota
    k8s.create_resource_quota(ns)
    logger.info(f"  Created ResourceQuota")

    # 3. PVC
    k8s.create_pvc(ns)
    logger.info(f"  Created PVC")

    # 4. htpasswd Secret
    b64users = generate_htpasswd_b64(username, password)
    k8s.create_htpasswd_secret(ns, username, b64users)
    logger.info(f"  Created htpasswd Secret")

    # 5. Middleware
    k8s.create_middleware(ns)
    logger.info(f"  Created Traefik Middleware")

    # 6. Deployment
    k8s.create_deployment(ns)
    logger.info(f"  Created ttyd Deployment")

    # 7. Service
    k8s.create_service(ns)
    logger.info(f"  Created ttyd Service")

    # 8. IngressRoute
    k8s.create_ingressroute(ns, host)
    logger.info(f"  Created IngressRoute ({host})")

    return get_friend_info(name)


def delete_friend(name: str) -> None:
    """Delete friend namespace (cascading delete)."""
    ns = f"friend-{name}"
    logger.info(f"Deleting friend {name} (namespace: {ns})")
    k8s.delete_namespace(ns)
    logger.info(f"  Deleted namespace {ns}")
