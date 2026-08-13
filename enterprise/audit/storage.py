"""MinIO storage helpers for procurement screenshots and quote PDFs."""

import asyncio
import io
import uuid
from datetime import UTC, datetime, timedelta

from minio import Minio

from skyvern.config import settings

DEFAULT_PRESIGN_EXPIRY = timedelta(hours=1)


def get_minio_client() -> Minio:
    if (
        not settings.MINIO_ENDPOINT
        or not settings.MINIO_ROOT_USER
        or not settings.MINIO_ROOT_PASSWORD
        or not settings.MINIO_ROOT_USER.get_secret_value()
        or not settings.MINIO_ROOT_PASSWORD.get_secret_value()
    ):
        raise RuntimeError("MinIO is not configured")
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ROOT_USER.get_secret_value(),
        secret_key=settings.MINIO_ROOT_PASSWORD.get_secret_value(),
        secure=settings.MINIO_USE_SSL,
    )


def generate_object_key(org_id: str, task_id: str, action_index: int, phase: str) -> str:
    if phase not in {"before", "after"}:
        raise ValueError("phase must be before or after")
    return f"audit/{org_id}/{task_id}/{action_index}_{phase}_{uuid.uuid4().hex[:12]}.png"


def generate_quote_object_key(org_id: str, task_id: str, _filename: str) -> str:
    return f"quotes/{org_id}/{task_id}/{uuid.uuid4().hex[:12]}.pdf"


def get_bucket_name(dt: datetime | None = None) -> str:
    return f"procurerpa-audit-{(dt or datetime.now(UTC)).strftime('%Y%m')}"


async def ensure_bucket_exists(minio_client: Minio, bucket_name: str) -> bool:
    exists = await asyncio.to_thread(minio_client.bucket_exists, bucket_name)
    if not exists:
        await asyncio.to_thread(minio_client.make_bucket, bucket_name)
        return True
    return False


async def upload_file(
    minio_client: Minio,
    bucket_name: str,
    object_key: str,
    data: bytes,
    content_type: str,
) -> str:
    await ensure_bucket_exists(minio_client, bucket_name)
    await asyncio.to_thread(
        minio_client.put_object,
        bucket_name,
        object_key,
        io.BytesIO(data),
        len(data),
        content_type=content_type,
    )
    return f"minio://{bucket_name}/{object_key}"


async def upload_screenshot(
    minio_client: Minio,
    bucket_name: str,
    object_key: str,
    data: bytes,
    content_type: str = "image/png",
) -> str:
    return await upload_file(minio_client, bucket_name, object_key, data, content_type)


async def get_presigned_url(
    minio_client: Minio,
    bucket_name: str,
    object_key: str,
    expiry: timedelta | None = None,
) -> str:
    return await asyncio.to_thread(
        minio_client.presigned_get_object,
        bucket_name,
        object_key,
        expires=expiry or DEFAULT_PRESIGN_EXPIRY,
    )


def split_minio_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("minio://"):
        raise ValueError("invalid MinIO URI")
    bucket, separator, object_key = uri[8:].partition("/")
    if not separator or not bucket or not object_key:
        raise ValueError("invalid MinIO URI")
    return bucket, object_key
