"""Generate and apply LiteLLM configuration from database models."""
from __future__ import annotations

import logging
import subprocess
from typing import Optional

import yaml

from models import ModelRecord

logger = logging.getLogger(__name__)

LITELLM_NAMESPACE = "litellm"
LITELLM_CONFIGMAP = "litellm-config"
LITELLM_CONFIG_KEY = "litellm_config.yaml"


def generate_config(models: list[ModelRecord]) -> str:
    """Generate litellm_config.yaml from database models.

    Models with api_key set to a non-empty value get the key inlined.
    Models with empty api_key get os.environ/<MODEL_ID_ENV> reference.
    """
    model_list = []
    for m in models:
        if not m.enabled:
            continue

        # Build litellm_params
        # OpenAI-compatible APIs need the openai/ prefix
        if m.api_type == "openai":
            params: dict = {"model": f"openai/{m.model_id}"}
        else:
            params: dict = {"model": m.model_id}

        if m.api_key:
            # Key provided — use it directly
            params["api_key"] = m.api_key
        else:
            # No key — reference env var (sanitize model_id for env name)
            env_name = m.model_id.replace("/", "_").replace("-", "_").upper()
            params["api_key"] = f"os.environ/{env_name}"

        if m.api_base:
            params["api_base"] = m.api_base

        # Anthropic models use a different parameter name
        if m.api_type == "anthropic":
            params["custom_llm_provider"] = "anthropic"

        model_list.append({
            "model_name": m.name,
            "litellm_params": params,
            "model_info": {
                "context_length": m.context_length,
                "max_tokens": m.max_tokens,
            },
        })

    config = {
        "model_list": model_list,
        "general_settings": {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
            "database_url": "os.environ/DATABASE_URL",
        },
        "litellm_settings": {
            "drop_params": True,
        },
    }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def apply_config(config_yaml: str) -> bool:
    """Write config to k8s ConfigMap and restart LiteLLM pod.

    Returns True on success, False on failure.
    """
    try:
        # Update ConfigMap
        cmd_map = [
            "kubectl", "create", "configmap", LITELLM_CONFIGMAP,
            "-n", LITELLM_NAMESPACE,
            f"--from-literal={LITELLM_CONFIG_KEY}={config_yaml}",
            "--dry-run=client", "-o", "yaml",
        ]
        result = subprocess.run(cmd_map, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error(f"ConfigMap dry-run failed: {result.stderr}")
            return False

        # Pipe to kubectl apply
        apply = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=result.stdout, capture_output=True, text=True, timeout=10,
        )
        if apply.returncode != 0:
            logger.error(f"ConfigMap apply failed: {apply.stderr}")
            return False

        # Restart LiteLLM pod
        restart = subprocess.run(
            ["kubectl", "rollout", "restart", "deployment/litellm", "-n", LITELLM_NAMESPACE],
            capture_output=True, text=True, timeout=10,
        )
        if restart.returncode != 0:
            logger.warning(f"LiteLLM restart failed (non-fatal): {restart.stderr}")

        logger.info("LiteLLM config updated and pod restarted")
        return True

    except Exception as e:
        logger.error(f"Failed to apply LiteLLM config: {e}")
        return False


def get_model_env_name(model_id: str) -> str:
    """Convert model ID to environment variable name.

    Example: 'minimaxai/minimax-m3' -> 'MINIMAXAI_MINIMAX_M3'
    """
    return model_id.replace("/", "_").replace("-", "_").upper()


def build_env_vars(models: list[ModelRecord]) -> dict[str, str]:
    """Build environment variable dict for models with api_key.

    Returns {ENV_NAME: api_key_value} for models that have api_keys set.
    """
    env = {}
    for m in models:
        if m.api_key and m.enabled:
            env[get_model_env_name(m.model_id)] = m.api_key
    return env
