import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
ENV_CONFIG_PATH = "REMOTE_TRANS_CONFIG"


class CredentialConfigError(Exception):
    """Raised when the credential config file is missing or incomplete."""


def resolve_config_path(config_arg: Optional[Path | str] = None) -> Path:
    """Return the credential config path honoring CLI, env, then default."""

    if config_arg:
        return Path(config_arg).expanduser()

    env_path = os.environ.get(ENV_CONFIG_PATH)
    if env_path:
        return Path(env_path).expanduser()

    return DEFAULT_CONFIG_PATH


def load_config(config_path: Optional[Path | str] = None) -> Dict[str, object]:
    """Load the shared JSON config for credentials and template IDs."""

    path = resolve_config_path(config_path)
    if not path.is_file():
        raise CredentialConfigError(f"credential config file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CredentialConfigError(f"failed to parse credential config: {exc}") from exc

    if not isinstance(data, dict):
        raise CredentialConfigError("credential config must be a JSON object")

    return data


def load_credentials(
    config_path: Optional[Path | str] = None, *, config_data: Optional[Dict[str, object]] = None
) -> Tuple[str, str]:
    data = config_data or load_config(config_path)

    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        raise CredentialConfigError("credential config must include 'username' and 'password'")

    return str(username), str(password)


def load_template_id(
    template_key: str,
    default: str,
    config_path: Optional[Path | str] = None,
    *,
    config_data: Optional[Dict[str, object]] = None,
) -> str:
    data = config_data or load_config(config_path)

    template_ids = data.get("template_ids")
    if isinstance(template_ids, dict):
        candidate = template_ids.get(template_key)
        if candidate:
            return str(candidate)

    return default
