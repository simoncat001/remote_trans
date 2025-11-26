import json
import os
from pathlib import Path
from typing import Optional, Tuple

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


def load_credentials(config_path: Optional[Path | str] = None) -> Tuple[str, str]:
    path = resolve_config_path(config_path)
    if not path.is_file():
        raise CredentialConfigError(f"credential config file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CredentialConfigError(f"failed to parse credential config: {exc}") from exc

    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        raise CredentialConfigError("credential config must include 'username' and 'password'")

    return str(username), str(password)
