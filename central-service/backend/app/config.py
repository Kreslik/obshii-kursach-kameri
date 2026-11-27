"""Настройки подключений центрального сервиса."""

import os


def load_settings() -> dict[str, str]:
    keys = (
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
        "POSTGRES_PASSWORD", "REDIS_URL", "MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY", "MINIO_BUCKET", "JWT_SECRET_KEY",
    )
    return {key: os.environ[key] for key in keys if key in os.environ}
