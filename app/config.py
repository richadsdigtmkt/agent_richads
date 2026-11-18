"""Configuración por variables de entorno (ver .env.example)."""

import glob
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:  # .env en la raíz del proyecto
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _from_client_json() -> tuple[str, str]:
    """Si no hay .env, lee el JSON de credenciales descargado de Google Cloud (client_secret_*.json)."""
    files = sorted(glob.glob(str(ROOT / "client_secret*.json")))
    if not files:
        return "", ""
    data = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    web = data.get("web") or data.get("installed") or {}
    return web.get("client_id", ""), web.get("client_secret", "")


_json_id, _json_secret = _from_client_json()


class Settings:
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID") or _json_id
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET") or _json_secret
    oauth_redirect_uri: str = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    # Desde el 09/09/2026 el token ya no decide el acceso (lo decide el proyecto de Google Cloud
    # de las credenciales OAuth). Se manda solo si está definido.
    developer_token: str = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    # MCC desde la que se leen cuentas vinculadas (solo para pruebas internas de RichAds).
    login_customer_id: str = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "8848753684")
    api_version: str = os.getenv("GOOGLE_ADS_API_VERSION", "v26")
    session_secret: str = os.getenv("SESSION_SECRET") or os.urandom(24).hex()


settings = Settings()
