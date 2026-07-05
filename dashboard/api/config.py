"""Dashboard API configuration from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgresql"
    postgres_port: int = 5432
    postgres_user: str = "dashboard-admin"
    postgres_password: str = "dash-pass-2026"
    postgres_db: str = "hermes_dashboard"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "dashboard-admin"
    minio_secret_key: str = "dash-pass-2026"
    minio_bucket: str = "hermes-states"
    minio_secure: bool = False

    # Kubernetes
    k8s_incluster: bool = True

    # Friend defaults
    friend_storage_class: str = "local-path"
    friend_storage_size: str = "2Gi"
    friend_image: str = "localhost/hermes-friends/ttyd:latest"
    friend_cpu_request: str = "250m"
    friend_memory_request: str = "256Mi"
    friend_cpu_limit: str = "1"
    friend_memory_limit: str = "512Mi"
    friend_domain: str = "hermes.caron.fun"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:***@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
