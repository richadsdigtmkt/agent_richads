"""Cliente mínimo de la API de Google Ads por REST (searchStream), siempre en UTF-8.

Se usa REST con httpx en lugar de la librería oficial para controlar la versión de la API
y evitar los problemas de codificación del conector de escritorio (caracteres no ASCII).
Solo lectura: este módulo no tiene ninguna operación de escritura.
"""

from __future__ import annotations

import httpx

from app.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/adwords"


class AdsApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return str(httpx.URL(AUTH_URL, params=params))


def exchange_code(code: str) -> dict:
    r = httpx.post(TOKEN_URL, data={
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.oauth_redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=20)
    r.raise_for_status()
    return r.json()


def refresh_access_token(refresh_token: str) -> str:
    r = httpx.post(TOKEN_URL, data={
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    }, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


class AdsClient:
    def __init__(self, access_token: str, login_customer_id: str | None = None):
        self.base = f"https://googleads.googleapis.com/{settings.api_version}"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if settings.developer_token:
            self.headers["developer-token"] = settings.developer_token
        self.access_token = access_token
        # None = usar la MCC de config; "" = sin cabecera (acceso directo a la cuenta)
        lcid = settings.login_customer_id if login_customer_id is None else login_customer_id
        self.login_customer_id = lcid
        if lcid:
            self.headers["login-customer-id"] = lcid.replace("-", "")

    def _raise(self, r: httpx.Response) -> None:
        try:
            err = r.json()
            if isinstance(err, list):
                err = err[0]
            details = err["error"].get("details", [{}])
            code = "UNKNOWN"
            for d in details:
                for e in d.get("errors", []):
                    code = next(iter(e.get("errorCode", {}).values()), code)
            raise AdsApiError(r.status_code, code, err["error"].get("message", ""))
        except (ValueError, KeyError, IndexError, TypeError):
            raise AdsApiError(r.status_code, "UNKNOWN", r.text[:300])

    def list_accessible_customers(self) -> list[str]:
        r = httpx.get(f"{self.base}/customers:listAccessibleCustomers", headers=self.headers, timeout=30)
        if r.status_code != 200:
            self._raise(r)
        return [name.split("/")[-1] for name in r.json().get("resourceNames", [])]

    def search(self, customer_id: str, query: str) -> list[dict]:
        cid = customer_id.replace("-", "")
        r = httpx.post(
            f"{self.base}/customers/{cid}/googleAds:searchStream",
            headers=self.headers,
            content=_json_utf8({"query": query}),
            timeout=120,
        )
        if r.status_code != 200:
            self._raise(r)
        r.encoding = "utf-8"
        rows: list[dict] = []
        for batch in r.json():
            rows.extend(batch.get("results", []))
        return rows


def _json_utf8(obj: dict) -> bytes:
    import json

    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
