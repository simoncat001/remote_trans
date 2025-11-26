import json
from pathlib import Path
from typing import Tuple

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


class CredentialConfigError(Exception):
    """Raised when the credential config file is missing or incomplete."""


def load_credentials(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Tuple[str, str]:
    path = Path(config_path).expanduser()
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
