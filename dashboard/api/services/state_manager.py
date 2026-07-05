"""State save/restore service — tar-based backup via kubectl exec."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from typing import Optional

from services import k8s
from services.minio_client import upload_state, list_snapshots, download_snapshot

logger = logging.getLogger(__name__)

# Only backup Hermes-relevant paths (skip large npm/node caches)
BACKUP_PATHS = [".hermes", ".bashrc", ".profile"]


def save_state(friend_name: str) -> str:
    """Save friend state by exec-ing into running ttyd pod.

    Creates a tarball of essential Hermes files, streams it out via kubectl,
    uploads to MinIO. Returns the snapshot key.
    """
    ns = f"friend-{friend_name}"
    pods = k8s.get_running_pods(ns, label_selector="app=ttyd")
    if not pods:
        raise ValueError(f"No running ttyd pod found in {ns}")

    pod_name = pods[0]
    logger.info(f"Saving state for {friend_name} via pod {pod_name}")

    # Build tar command for only essential paths
    paths_str = " ".join(BACKUP_PATHS)
    tar_cmd = f"tar czf - -C /root {paths_str}"

    # Use kubectl exec to stream the tarball out directly
    kubectl_cmd = [
        "kubectl", "-n", ns, "exec", pod_name, "--",
        "sh", "-c", tar_cmd,
    ]

    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            result = subprocess.run(
                kubectl_cmd,
                stdout=tmp,
                stderr=subprocess.PIPE,
                timeout=120,
            )
            tmp_path = tmp.name

        if result.returncode != 0:
            stderr_msg = result.stderr.decode(errors="replace")
            raise RuntimeError(f"kubectl exec failed (rc={result.returncode}): {stderr_msg}")

        file_size = os.path.getsize(tmp_path)
        logger.info(f"  tarball size: {file_size} bytes")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl exec timed out for {ns}/{pod_name}")
    except Exception as e:
        raise RuntimeError(f"Failed to stream tarball from {ns}/{pod_name}: {e}")

    # Read tarball and upload to MinIO
    timestamp = int(time.time())
    key = f"{friend_name}/backup-{timestamp}.tar.gz"

    with open(tmp_path, "rb") as f:
        data = f.read()

    upload_state(friend_name, data, key)

    # Cleanup temp file
    os.unlink(tmp_path)

    logger.info(f"  State saved to {key} ({len(data)} bytes)")
    return key


def get_snapshots(friend_name: str) -> list:
    """List available snapshots for a friend."""
    return list_snapshots(friend_name)


def restore_state(friend_name: str, snapshot_key: str) -> dict:
    """Restore state from a snapshot via kubectl exec into the running ttyd pod.

    Downloads tarball from MinIO into a temp file, then streams it into the
    pod via kubectl exec and extracts to /root/.
    Returns status dict.
    """
    ns = f"friend-{friend_name}"
    logger.info(f"Restoring state for {friend_name} from {snapshot_key}")

    pods = k8s.get_running_pods(ns, label_selector="app=ttyd")
    if not pods:
        raise ValueError(f"No running ttyd pod found in {ns}")

    pod_name = pods[0]

    # Download snapshot from MinIO
    try:
        data = download_snapshot(snapshot_key)
        logger.info(f"  downloaded snapshot: {len(data)} bytes")
    except Exception as e:
        raise RuntimeError(f"Failed to download snapshot from MinIO: {e}")

    # Write to temp file and pipe into the pod
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with open(tmp_path, "wb") as f:
            f.write(data)

        # Stream the tar into the pod and extract to /root/
        kubectl_cmd = [
            "kubectl", "-n", ns, "exec", "-i", pod_name, "--",
            "sh", "-c", "tar xzf - -C /root",
        ]

        with open(tmp_path, "rb") as f:
            result = subprocess.run(
                kubectl_cmd,
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
            )

        if result.returncode != 0:
            stderr_msg = result.stderr.decode(errors="replace")
            raise RuntimeError(f"kubectl exec failed (rc={result.returncode}): {stderr_msg}")

        logger.info(f"  State restored to {pod_name}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"kubectl exec timed out for {ns}/{pod_name}")
    finally:
        os.unlink(tmp_path)

    return {
        "status": "restored",
        "snapshot_key": snapshot_key,
        "pod": pod_name,
    }
