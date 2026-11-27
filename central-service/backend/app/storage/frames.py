"""Хранение снимков в MinIO с однократной записью по каждому frame_key."""

from contextlib import closing, contextmanager
from hashlib import sha256

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class FrameConflict(Exception):
    """Указанный ключ уже занят снимком с другим содержимым."""


class StorageUnavailable(Exception):
    """Хранилище не смогло записать или проверить снимок."""


@contextmanager
def _storage():
    config = current_app.config
    try:
        endpoint = config["MINIO_ENDPOINT"]
        bucket = config["MINIO_BUCKET"]
        access_key = config["MINIO_ACCESS_KEY"]
        secret_key = config["MINIO_SECRET_KEY"]
        if not all((endpoint, bucket, access_key, secret_key)):
            raise StorageUnavailable("Не заданы параметры подключения к MinIO.")
        if "://" not in endpoint:
            endpoint = f"http://{endpoint}"
        client = boto3.session.Session().client(
            "s3",
            endpoint_url=endpoint,
            region_name="us-east-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=3,
                read_timeout=10,
                retries={"mode": "standard", "total_max_attempts": 2},
            ),
        )
        with closing(client):
            yield client, bucket
    except (BotoCoreError, ClientError, KeyError, OSError, ValueError) as error:
        raise StorageUnavailable("Не удалось выполнить операцию со снимком в MinIO.") from error


def _matches(client, bucket: str, key: str, digest: str) -> bool:
    head = client.head_object(Bucket=bucket, Key=key)
    stored_digest = head.get("Metadata", {}).get("sha256")
    if stored_digest:
        return stored_digest == digest

    # Снимки, загруженные без метаданных, сверяются по содержимому.
    response = client.get_object(Bucket=bucket, Key=key, IfMatch=head["ETag"])
    stored = sha256()
    with closing(response["Body"]) as body:
        for chunk in body.iter_chunks(chunk_size=64 * 1024):
            stored.update(chunk)
    return stored.hexdigest() == digest


def frame_matches(key: str, data: bytes) -> bool:
    """Сравнивает переданные байты с сохранённым кадром по тому же ключу."""
    with _storage() as (client, bucket):
        return _matches(client, bucket, key, sha256(data).hexdigest())


def _create_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as error:
        # Другой воркер мог создать наш бакет после получения NoSuchBucket.
        if error.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise


def put_frame(key: str, data: bytes) -> None:
    """Сохраняет снимок или подтверждает повторную доставку идентичных байтов."""
    digest = sha256(data).hexdigest()
    with _storage() as (client, bucket):
        for attempt in range(3):
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=data,
                    ContentType="image/jpeg",
                    Metadata={"sha256": digest},
                    IfNoneMatch="*",
                )
                return
            except ClientError as error:
                code = error.response["Error"]["Code"]
                status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if code == "PreconditionFailed" or status == 412:
                    if _matches(client, bucket, key, digest):
                        return
                    raise FrameConflict("Под этим frame_key уже хранится другой снимок.") from error
                if attempt == 2:
                    raise
                if code == "NoSuchBucket":
                    _create_bucket(client, bucket)
                elif code != "ConditionalRequestConflict" and status != 409:
                    raise
