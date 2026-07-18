"""Dashboard API configuration from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgresql.dashboard.svc.cluster.local"
    postgres_port: int = 5432
    postgres_user: str = "hermes"
    postgres_password: str = "hermes_db_pass_2026"
    postgres_db: str = "dashboard"

    # LiteLLM
    litellm_host: str = "litellm.litellm.svc.cluster.local"
    litellm_port: int = 4000
    litellm_master_key: str = ""

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
    friend_domain: str = ""
    tls_cert_resolver: str = "cfresolver"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
