"""Web mínima: conectar Google Ads, elegir cuenta, formulario de alta e informe gratuito.

Esqueleto: los tokens se guardan en memoria del proceso (se pierden al reiniciar).
Antes de producción: base de datos con los refresh tokens cifrados.
"""

from __future__ import annotations

import secrets
from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.ads.client import AdsApiError, AdsClient, auth_url, exchange_code, refresh_access_token
from app.ads.loader import load_account
from app.ads.models import Profile
from app.config import settings
from app.report.free import build_free_report
from app.rules.engine import run_rules

app = FastAPI(title="RichAds: diagnóstico de Google Ads")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, https_only=False)

_TOKENS: dict[str, str] = {}  # sesión -> refresh token (solo esqueleto)


def page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>RichAds: diagnóstico de Google Ads</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 16px;line-height:1.5;color:#1d2433}}
h1{{font-size:1.5rem}}.btn{{background:#1a56db;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;border:0;font-size:1rem;cursor:pointer}}
.score{{font-size:2.4rem;font-weight:700}}.sev{{font-size:.8rem;padding:2px 8px;border-radius:10px;background:#eef;margin-right:6px}}
label{{display:block;margin-top:12px}}select,input{{padding:6px;font-size:1rem}}.muted{{color:#667}}</style></head>
<body>{body}</body></html>""")


@app.get("/", response_class=HTMLResponse)
def home():
    return page("""<h1>Diagnóstico de tu cuenta de Google Ads</h1>
<p>Conecta tu cuenta con acceso de solo lectura y recibe una revisión de los puntos que más pueden estar
afectando a tus resultados. No se cambia nada en tu cuenta.</p>
<p><a class="btn" href="/auth/start">Conectar Google Ads</a></p>
<p class="muted">Los datos se procesan con herramientas de IA de terceros (Anthropic) solo para generar tu informe.</p>""")


@app.get("/auth/start")
def auth_start(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["state"] = state
    return RedirectResponse(auth_url(state))


@app.get("/auth/callback")
def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or state != request.session.get("state"):
        return page("<h1>No se pudo conectar</h1><p>Vuelve a intentarlo.</p><p><a href='/'>Volver</a></p>")
    tokens = exchange_code(code)
    sid = request.session.get("sid") or secrets.token_urlsafe(16)
    request.session["sid"] = sid
    if "refresh_token" in tokens:
        _TOKENS[sid] = tokens["refresh_token"]
    return RedirectResponse("/cuentas")


def _client(request: Request) -> AdsClient | None:
    rt = _TOKENS.get(request.session.get("sid", ""))
    return AdsClient(refresh_access_token(rt)) if rt else None


@app.get("/cuentas", response_class=HTMLResponse)
def accounts(request: Request):
    client = _client(request)
    if not client:
        return RedirectResponse("/")
    try:
        ids = client.list_accessible_customers()
    except AdsApiError as e:
        return page(f"<h1>Error de acceso</h1><p>{escape(e.code)}</p>")
    options = "".join(f"<option value='{i}'>{i[:3]}-{i[3:6]}-{i[6:]}</option>" for i in ids)
    return page(f"""<h1>Elige la cuenta y cuéntanos tu negocio</h1>
<form method="post" action="/informe">
<label>Cuenta <select name="customer_id">{options}</select></label>
<label>Tipo de negocio <select name="business_type"><option value="leads">Captación de contactos</option>
<option value="ecommerce">Tienda online</option><option value="mixto">Mixto</option></select></label>
<label>Ticket medio o valor de un cliente <input name="avg_ticket" type="number" step="any"></label>
<label>Margen aproximado <select name="margin_band"><option value="">Prefiero no decirlo</option>
<option>&lt;20</option><option>20-40</option><option>&gt;40</option></select></label>
<label>Contactos o pedidos reales al mes <input name="real_results_month" type="number" step="any"></label>
<label>¿Crees que Google Ads te está funcionando? <select name="channel_works"><option value="si">Sí</option>
<option value="no">No</option><option value="no_se">No lo sé</option></select></label>
<label>Nombre de tu marca (para separar la campaña de marca) <input name="brand_terms"></label>
<p><button class="btn" type="submit">Ver diagnóstico gratuito</button></p></form>""")


@app.post("/informe", response_class=HTMLResponse)
def report(
    request: Request,
    customer_id: str = Form(...),
    business_type: str = Form("desconocido"),
    avg_ticket: str = Form(""),
    margin_band: str = Form(""),
    real_results_month: str = Form(""),
    channel_works: str = Form(""),
    brand_terms: str = Form(""),
):
    client = _client(request)
    if not client:
        return RedirectResponse("/", status_code=303)
    profile = Profile(
        business_type=business_type,
        avg_ticket=float(avg_ticket) if avg_ticket else None,
        margin_band=margin_band or None,
        real_results_month=float(real_results_month) if real_results_month else None,
        channel_works=channel_works or None,
        brand_terms=[t.strip() for t in brand_terms.split(",") if t.strip()],
    )
    try:
        data = load_account(client, customer_id, profile)
    except AdsApiError as e:
        return page(f"<h1>No se pudo leer la cuenta</h1><p>{escape(e.code)}: {escape(e.message)}</p>")
    r = build_free_report(run_rules(data))
    areas = "".join(
        f"<h3>{escape(a)}</h3><ul>" + "".join(f"<li><span class='sev'>{escape(s)}</span>{escape(t)}</li>" for s, t in items) + "</ul>"
        for a, items in r.areas
    )
    no = f"<p class='muted'>No revisado: {escape('; '.join(r.not_observed))}.</p>" if r.not_observed else ""
    return page(f"""<h1>Diagnóstico gratuito</h1><p class="score">{(str(r.score) + "/100") if r.level != "Demasiado pronto para puntuar" else ""}</p><p>{escape(r.level)}</p>
{areas}{no}<p>El informe completo explica la causa de cada punto, con cifras y un plan de acción priorizado,
revisado por un especialista antes de la entrega.</p>""")
