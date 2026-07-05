"""MinIO client wrapper for state management."""
from __future__ import annotations

import logging
from typing import Optional

from minio import Minio
from minio.error import S3Error

from config import settings
from models import FriendSnapshot

logger = logging.getLogger(__name__)


def get_client() -> Minio:
    """Create a MinIO client."""
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    """Ensure the states bucket exists."""
    client = get_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info(f"Created MinIO bucket: {settings.minio_bucket}")


def upload_state(friend_name: str, data: bytes, key: str) -> None:
    """Upload state tarball to MinIO."""
    client = get_client()
    ensure_bucket()
    from io import BytesIO
    client.put_object(
        settings.minio_bucket,
        key,
        BytesIO(data),
        length=len(data),
        content_type="application/gzip",
    )
    logger.info(f"Uploaded state for {friend_name} to {key}")


def list_snapshots(friend_name: str) -> list[FriendSnapshot]:
    """List all snapshots for a friend."""
    client = get_client()
    ensure_bucket()
    prefix = f"{friend_name}/"
    snapshots = []
    try:
        objects = client.list_objects(settings.minio_bucket, prefix=prefix)
        for obj in objects:
            if obj.object_name.endswith(".tar.gz"):
                snapshots.append(FriendSnapshot(
                    key=obj.object_name,
                    size=obj.size or 0,
                    last_modified=obj.last_modified,
                ))
    except S3Error as e:
        logger.error(f"Error listing snapshots for {friend_name}: {e}")
    return sorted(snapshots, key=lambda s: s.last_modified or "", reverse=True)


def download_snapshot(key: str) -> bytes:
    """Download a snapshot from MinIO."""
    client = get_client()
    response = client.get_object(settings.minio_bucket, key)
    try:
        data = response.read()
    finally:
        response.close()
        response.release_conn()
    return data


def get_snapshot_url(key: str, expires: int = 3600) -> str:
    """Get a presigned URL for downloading a snapshot."""
    client = get_client()
    return client.presigned_get_object(settings.minio_bucket, key, expires=expires)
