"""Configuración por variables de entorno (ver .env.example)."""

import os


class Settings:
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    oauth_redirect_uri: str = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    # Desde el 09/09/2026 el token ya no decide el acceso (lo decide el proyecto de Google Cloud
    # de las credenciales OAuth). Se manda solo si está definido.
    developer_token: str = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    # MCC desde la que se leen cuentas vinculadas (solo para pruebas internas de RichAds).
    login_customer_id: str = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")
    api_version: str = os.getenv("GOOGLE_ADS_API_VERSION", "v26")
    session_secret: str = os.getenv("SESSION_SECRET", "cambiar-en-produccion")


settings = Settings()
