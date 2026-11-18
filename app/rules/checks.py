"""Reglas del diagnóstico. Cada una cita el paso del checklist v4 en el que se basa."""

from __future__ import annotations

import re
from statistics import median

from app.ads.models import AccountData, Campaign
from app.rules.engine import Finding, NotObserved, rule

BRAND_NAME_RE = re.compile(r"(brand|branding|marca|marke|markenname)", re.I)
SMART_BIDDING = {"TARGET_CPA", "TARGET_ROAS", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"}
CONTACT_CATEGORIES = {"CONTACT", "PHONE_CALL_LEAD", "GET_DIRECTIONS", "OUTBOUND_CLICK", "ENGAGEMENT", "PAGE_VIEW"}
LEAD_CATEGORIES = {
    "SUBMIT_LEAD_FORM", "IMPORTED_LEAD", "QUALIFIED_LEAD", "CONVERTED_LEAD", "SIGNUP",
    "CONTACT", "BOOK_APPOINTMENT", "REQUEST_QUOTE", "PHONE_CALL_LEAD",
}
LOW_N = 4  # paso 0-bis: con 4 conversiones o menos, CPA y ROAS no tienen señal


def _share(part: float, total: float) -> float:
    return part / total if total else 0.0


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def _n(n: int, sing: str, plur: str) -> str:
    return f"{n} {sing if n == 1 else plur}"


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _money(x: float, cur: str) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {cur}".strip()


def _spending(d: AccountData) -> list[Campaign]:
    return [c for c in d.campaigns if c.cost > 0]


def _is_new(c: Campaign, d: AccountData) -> bool:
    if c.start_date and (d.today - c.start_date).days <= 14:
        return True
    if c.cost_7d is not None and c.cost > 0 and c.cost_7d / c.cost >= 0.85 and d.period_days >= 30:
        return True
    return False


def is_brand(c: Campaign, d: AccountData) -> bool:
    if BRAND_NAME_RE.search(c.name):
        return True
    return any(t.lower() in c.name.lower() for t in d.profile.brand_terms if t)


# --- Paso 0: terreno ---------------------------------------------------------------------------

@rule
def zero_spend(d: AccountData) -> list[Finding]:
    if d.total_cost >= 1:
        return []
    enabled = [c for c in d.campaigns if c.active]
    if enabled:
        return [Finding(
            "zero_spend", "0", "terreno", "alta",
            "Hay campañas activas que no están gastando nada.",
            f"{len(enabled)} campañas ENABLED con gasto cero en {d.period_days} días: es bloqueo de entrega, "
            "no decisión comercial (principio 36). Descartar en este orden: verificación de anunciante, "
            "facturación, presupuesto a cero, suspensión de cuenta o de política, campaña recién encendida.",
            {"enabled": len(enabled)},
        )]
    return [Finding(
        "zero_spend", "0", "terreno", "info",
        "La cuenta no tiene campañas activas.",
        "Todo pausado y gasto cero: decisión de negocio, no fallo de cuenta.",
    )]


@rule
def eu_political(d: AccountData) -> list[Finding]:
    known = [c for c in d.campaigns if c.active and c.eu_political is not None]
    pending = [c for c in known if c.eu_political not in (
        "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING", "CONTAINS_EU_POLITICAL_ADVERTISING")]
    if not pending:
        return []
    return [Finding(
        "eu_political", "0", "terreno", "baja",
        "Falta una declaración obligatoria en algunas campañas activas.",
        f"{len(pending)} campañas activas sin declaración de EU political ads. Desde el 01/04/2026 la API y "
        "los scripts fallan en cualquier modificación mientras quede una campaña sin declarar. "
        "Corrección: declarar \"No\" a nivel de cuenta.",
        {"campaigns": [c.name for c in pending]},
    )]


# --- Paso 0-bis: ventana y n -------------------------------------------------------------------

@rule
def new_campaigns(d: AccountData) -> list[Finding]:
    spending = _spending(d)
    new = [c for c in spending if _is_new(c, d)]
    if not new:
        return []
    share = _share(sum(c.cost for c in new), d.total_cost)
    sev = "media" if share >= 0.5 else "info"
    symptom = (
        "La mayor parte del gasto está en campañas recién lanzadas: todavía es pronto para juzgar su rendimiento."
        if share >= 0.5 else
        "Hay campañas recién lanzadas que todavía no tienen datos suficientes."
    )
    rows = [f"{c.name}: {_pct(_share(c.cost_7d or 0, c.cost))} de su gasto de 30 días cae en los últimos 7"
            + (f" (inicio {c.start_date.isoformat()})" if c.start_date else "") for c in new]
    return [Finding(
        "new_campaigns", "0-bis", "datos", sev, symptom,
        f"{len(new)} campañas con gasto concentrado en la última semana, {_pct(share)} del gasto de la cuenta. "
        "No se propone ningún cambio estructural con una sola lectura (freno 10b). " + "; ".join(rows),
        {"campaigns": [c.name for c in new], "spend_share": share},
    )]


@rule
def low_signal(d: AccountData) -> list[Finding]:
    low = [c for c in _spending(d) if c.conversions <= LOW_N]
    if not low:
        return []
    share = _share(sum(c.cost for c in low), d.total_cost)
    sev = "baja" if share >= 0.5 else "info"
    return [Finding(
        "low_signal", "0-bis", "datos", sev,
        "Algunas campañas tienen tan pocas conversiones que su coste por conversión no es fiable.",
        f"{len(low)} campañas con {LOW_N} conversiones o menos en {d.period_days} días ({_pct(share)} del gasto): "
        "CPA y ROAS sin señal. Impresiones, clics, CTR y CPC sí se pueden leer.",
        {"campaigns": {c.name: c.conversions for c in low}, "spend_share": share},
    )]


# --- Paso 1: signos, composición y precio ------------------------------------------------------

@rule
def zero_conv_spend(d: AccountData) -> list[Finding]:
    zero = [c for c in _spending(d) if c.conversions == 0]
    if not zero:
        return []
    share = _share(sum(c.cost for c in zero), d.total_cost)
    if share < 0.02:
        return []
    sev = "media" if share >= 0.2 else "baja"
    new_names = {c.name for c in zero if _is_new(c, d)}
    return [Finding(
        "zero_conv_spend", "1b", "gasto", sev,
        "Parte del presupuesto va a campañas que no registran ninguna conversión.",
        f"{_pct(share)} del gasto ({_money(sum(c.cost for c in zero), d.currency)}) en {len(zero)} campañas con "
        f"0 conversiones en {d.period_days} días"
        + (". Si supera el 20-30 %, el CPA de cuenta no se interpreta" if share >= 0.2 else "")
        + (f". Recién lanzadas: {', '.join(sorted(new_names))}" if new_names else "") + ".",
        {"campaigns": {c.name: c.cost for c in zero}, "spend_share": share},
    )]


@rule
def brand_composition(d: AccountData) -> list[Finding]:
    if d.total_conversions <= 0:
        return []
    brand = [c for c in _spending(d) if is_brand(c, d)]
    if not brand:
        return []
    s = _share(sum(c.cost for c in brand), d.total_cost)
    cv = _share(sum(c.conversions for c in brand), d.total_conversions)
    v = _share(sum(c.conv_value for c in brand), d.total_value)
    if cv - s < 0.15 and v - s < 0.15:
        return []
    nb_cost = d.total_cost - sum(c.cost for c in brand)
    nb_conv = d.total_conversions - sum(c.conversions for c in brand)
    nb_val = d.total_value - sum(c.conv_value for c in brand)
    b_cost = sum(c.cost for c in brand)
    b_val = sum(c.conv_value for c in brand)
    detail = (
        f"Marca: {_pct(s)} del gasto, {_pct(cv)} de las conversiones y {_pct(v)} del valor. "
        f"ROAS de marca {_ratio(b_val, b_cost)} frente a {_ratio(nb_val, nb_cost)} sin marca; "
        f"CPA sin marca {_money(nb_cost / nb_conv, d.currency) if nb_conv else 'sin conversiones'}. "
        "La marca recoge demanda que crean otros canales: el ROAS o CPA de cuenta se reporta siempre con la fila sin marca al lado."
    )
    return [Finding(
        "brand_composition", "1b", "gasto", "media",
        "El rendimiento global de la cuenta parece mejor de lo que es porque lo sostiene la campaña de marca.",
        detail, {"spend_share": s, "conv_share": cv, "value_share": v},
    )]


def _ratio(a: float, b: float) -> str:
    return f"{a / b:.2f}".replace(".", ",") if b else "n/d"


# --- Paso 4: integridad del tracking -----------------------------------------------------------

@rule
def proxy_pmax(d: AccountData) -> list[Finding]:
    pmax = [c for c in _spending(d) if c.channel == "PERFORMANCE_MAX"]
    search = [c for c in _spending(d) if c.channel == "SEARCH"]
    if not pmax or not search or d.total_conversions <= 0:
        return []
    p_cost, p_conv = sum(c.cost for c in pmax), sum(c.conversions for c in pmax)
    s_cost, s_conv = sum(c.cost for c in search), sum(c.conversions for c in search)
    if p_conv <= 0 or s_conv <= 0:
        return []
    conv_share = _share(p_conv, d.total_conversions)
    spend_share = _share(p_cost, d.total_cost)
    p_cpa, s_cpa = p_cost / p_conv, s_cost / s_conv
    if conv_share < 0.5 or spend_share > conv_share / 2 or p_cpa * 5 > s_cpa:
        return []
    zero_value = [c.name for c in pmax if c.conversions >= 100 and c.conv_value == 0]
    return [Finding(
        "proxy_pmax", "4c", "tracking", "alta",
        "Las conversiones de Performance Max no parecen medir lo mismo que las de búsqueda. "
        "El coste por conversión y el ROAS de la cuenta no son fiables hasta revisarlo.",
        f"Performance Max: {_pct(spend_share)} del gasto y {_pct(conv_share)} de las conversiones. "
        f"CPA PMax {_money(p_cpa, d.currency)} frente a {_money(s_cpa, d.currency)} en Search "
        f"({s_cpa / p_cpa:.1f}x). Patrón de conversión-proxy: una acción de contacto barata (clic a WhatsApp, "
        "teléfono o formulario visto) contada como principal, que Smart Bidding persigue. "
        + (f"Campañas con 100 o más conversiones y valor 0: {', '.join(zero_value)}. " if zero_value else "")
        + "No leer CPA ni ROAS de cuenta ni comparar conversiones entre PMax y Search. "
        "Confirmar en la configuración de acciones de conversión cuál es la principal.",
        {"pmax_conv_share": conv_share, "pmax_spend_share": spend_share, "pmax_cpa": p_cpa, "search_cpa": s_cpa,
         "zero_value_campaigns": zero_value},
    )]


@rule
def value_placeholder(d: AccountData) -> list[Finding]:
    conv, val = d.total_conversions, d.total_value
    if conv <= 0:
        return []
    if val == 0:
        sev = "info" if d.profile.business_type == "leads" else "media"
        return [Finding(
            "value_placeholder", "4b", "tracking", sev,
            "Las conversiones no registran ningún valor económico.",
            "Valor de conversión 0 en toda la cuenta: en captación de contactos puede ser intencionado; "
            "en tienda online es un fallo de medición. No se usa ROAS.",
        )]
    if 0.5 <= val / conv <= 1.5:
        return [Finding(
            "value_placeholder", "4b", "tracking", "baja" if d.profile.business_type != "ecommerce" else "media",
            "El valor de conversión parece un valor fijo de relleno, no un importe real.",
            f"Valor medio por conversión {val / conv:.2f}: típico de un valor por defecto de 1. No se usa ROAS.",
        )]
    return []


@rule
def value_irregular(d: AccountData) -> list[Finding]:
    conv_camps = [c for c in _spending(d) if c.conversions >= 20]
    zero_val = [c for c in conv_camps if c.conv_value == 0]
    with_val = [c for c in conv_camps if c.conv_value > 0]
    if len(zero_val) < 3 or len(with_val) < 3:
        return []
    round_vals = [c for c in with_val if round(c.conv_value) % 100 == 0]
    return [Finding(
        "value_irregular", "4b", "tracking", "media",
        "El valor de conversión llega solo en una parte de las campañas, así que el ROAS no es comparable entre ellas.",
        f"{len(zero_val)} campañas con 20 o más conversiones y valor 0, frente a {len(with_val)} con valor. "
        f"{len(round_vals)} de las que tienen valor muestran importes redondos, compatible con importación "
        "offline o valores fijos por acción. Antes de leer cualquier ROAS hay que saber qué acción aporta el valor.",
        {"zero_value": [c.name for c in zero_val], "round_values": [c.name for c in round_vals]},
    )]


@rule
def aov_outlier(d: AccountData) -> list[Finding]:
    camps = [c for c in _spending(d) if c.conversions >= 1 and c.conv_value > 0]
    if len(camps) < 3:
        return []
    aovs = {c.name: c.conv_value / c.conversions for c in camps}
    med = median(aovs.values())
    out = {n: a for n, a in aovs.items() if med > 0 and a > 20 * med}
    if not out:
        return []
    name, a = max(out.items(), key=lambda kv: kv[1])
    return [Finding(
        "aov_outlier", "4b", "tracking", "alta",
        "Una campaña registra un valor por conversión fuera de escala que distorsiona el ROAS de toda la cuenta.",
        f"{name}: valor medio por conversión {_money(a, d.currency)} frente a una mediana de "
        f"{_money(med, d.currency)} ({a / med:.0f}x). Suele ser un pedido de prueba, un separador decimal "
        "mal leído o un pedido fuera de escala. Corregir el valor antes de tocar puja o presupuesto: entra en Smart Bidding.",
        {"outliers": out, "median": med},
    )]


@rule
def conversion_actions(d: AccountData) -> list[Finding]:
    if not d.conversion_actions:
        return []
    out: list[Finding] = []
    primaries = [a for a in d.conversion_actions if a.primary and a.status == "ENABLED"]
    contact = [a for a in primaries if a.category in CONTACT_CATEGORIES]
    if contact:
        out.append(Finding(
            "conv_contact_primary", "4c", "tracking", "alta",
            "Una acción de contacto de poco valor cuenta como conversión principal y orienta la puja.",
            "Acciones principales de tipo contacto: " + ", ".join(f"{a.name} ({a.category})" for a in contact)
            + ". Pasarlas a secundarias deja la puja orientada al resultado real.",
            {"actions": [a.name for a in contact]},
        ))
    many = [a for a in primaries if a.counting_type == "MANY_PER_CLICK" and a.category in LEAD_CATEGORIES]
    if many and d.profile.business_type != "ecommerce":
        out.append(Finding(
            "conv_many_per_click", "4e", "tracking", "media",
            "Las conversiones de contacto se cuentan varias veces por usuario.",
            "Acciones de lead con recuento \"cada una\": " + ", ".join(a.name for a in many)
            + ". En captación infla el volumen (recargas de la página de gracias, doble envío). "
            "Al pasar a \"una\" el volumen baja y el CPA aparente sube: es corrección, no pérdida.",
            {"actions": [a.name for a in many]},
        ))
    purchases = [a for a in primaries if a.category == "PURCHASE"]
    if len(purchases) >= 2:
        out.append(Finding(
            "conv_double_count", "4a", "tracking", "alta",
            "Varias acciones principales podrían estar contando la misma venta.",
            "Acciones principales de compra: " + ", ".join(a.name for a in purchases)
            + ". Si miden la misma venta, Smart Bidding ve un valor inflado y puja más agresivo.",
            {"actions": [a.name for a in purchases]},
        ))
    return out


# --- Paso 2 y 3: cuota de impresiones y Quality Score ------------------------------------------

@rule
def budget_lost(d: AccountData) -> list[Finding]:
    camps = [c for c in _spending(d) if c.budget_lost_is is not None and c.budget_lost_is >= 0.2 and c.conversions > LOW_N]
    if not camps:
        return []
    return [Finding(
        "budget_lost", "2", "gasto", "baja",
        "Algunas campañas que convierten se quedan sin presupuesto y pierden impresiones.",
        "Cuota perdida por presupuesto: " + ", ".join(f"{c.name} {_pct(c.budget_lost_is)}" for c in camps)
        + ". Antes de subir presupuesto, confirmar que su CPA es rentable con el margen del cliente.",
        {"campaigns": {c.name: c.budget_lost_is for c in camps}},
    )]


@rule
def qs_low_spend(d: AccountData) -> list[Finding]:
    search_cost = sum(c.cost for c in d.campaigns if c.channel == "SEARCH")
    if not d.keywords or search_cost <= 0:
        return []
    low = [k for k in d.keywords if isinstance(k.quality_score, int) and k.quality_score < 5 and k.cost > 0]
    low_cost = sum(k.cost for k in low)
    if _share(low_cost, search_cost) < 0.05:
        return []
    top = sorted(low, key=lambda k: k.cost, reverse=True)[:5]
    return [Finding(
        "qs_low_spend", "3", "calidad", "media",
        "Varias palabras clave con mucho gasto tienen un nivel de calidad bajo, lo que encarece cada clic.",
        f"Keywords con QS menor que 5: {_pct(_share(low_cost, search_cost))} del gasto de Search. Principales: "
        + "; ".join(f"\"{k.text}\" ({k.campaign}) QS {k.quality_score}, {_money(k.cost, d.currency)}" for k in top)
        + ". Priorizar gasto alto con QS bajo, no scores bajos aislados (principio 8).",
        {"keywords": [(k.text, k.campaign, k.quality_score, k.cost) for k in top], "spend_share": _share(low_cost, search_cost)},
    )]


@rule
def match_type_cost_gap(d: AccountData) -> list[Finding]:
    """La misma keyword en frase y exacta: la frase paga mucho más por clic y no convierte."""
    out_rows = []
    by_key: dict[tuple[str, str], dict[str, list]] = {}
    for k in d.keywords:
        by_key.setdefault((k.campaign, k.text.lower()), {}).setdefault(k.match_type, []).append(k)
    for (camp, text), types in by_key.items():
        if "EXACT" not in types or not ({"PHRASE", "BROAD"} & types.keys()):
            continue
        ex = types["EXACT"]
        loose = types.get("PHRASE", []) + types.get("BROAD", [])
        ex_clicks, ex_cost = sum(k.clicks for k in ex), sum(k.cost for k in ex)
        lo_clicks, lo_cost = sum(k.clicks for k in loose), sum(k.cost for k in loose)
        lo_conv = sum(k.conversions for k in loose)
        if ex_clicks and lo_clicks >= 5 and lo_conv == 0:
            ex_cpc, lo_cpc = ex_cost / ex_clicks, lo_cost / lo_clicks
            if lo_cpc >= 3 * ex_cpc:
                out_rows.append((camp, text, lo_cost, lo_cpc, ex_cpc))
    if not out_rows:
        return []
    camps = {r[0] for r in out_rows}
    camp_cost = sum(c.cost for c in d.campaigns if c.name in camps)
    loose_cost = sum(r[2] for r in out_rows)
    if _share(loose_cost, camp_cost) < 0.15:
        return []
    return [Finding(
        "match_type_cost_gap", "8", "busqueda", "baja",
        "Las variantes amplias de algunas palabras clave pagan mucho más por clic que la versión exacta y no convierten.",
        f"{_pct(_share(loose_cost, camp_cost))} del gasto de esas campañas en variantes de frase o amplia sin conversiones: "
        + "; ".join(f"\"{t}\" CPC {_money(lc, d.currency)} frente a {_money(ec, d.currency)} en exacta" for _, t, _, lc, ec in out_rows[:4])
        + ". Suele indicar subastas con revendedores o competidores; confirmar con los términos de búsqueda.",
        {"keywords": [r[1] for r in out_rows], "spend_share": _share(loose_cost, camp_cost)},
    )]


# --- Paso 5: estructura e higiene --------------------------------------------------------------

@rule
def hygiene(d: AccountData) -> list[Finding]:
    total = len(d.campaigns)
    if total == 0:
        return []
    paused = [c for c in d.campaigns if not c.active]
    paused_cost = [c for c in paused if c.cost > 0]
    zombies = [c for c in d.campaigns if c.active and c.impressions == 0]
    out: list[Finding] = []
    pc_share = _share(sum(c.cost for c in paused_cost), d.total_cost)
    if paused_cost:
        out.append(Finding(
            "paused_with_spend", "5", "estructura", "baja",
            "Se pausó alguna campaña a mitad de periodo.",
            f"{_n(len(paused_cost), 'campaña pausada', 'campañas pausadas')} con gasto en la ventana ({_pct(pc_share)} del gasto): "
            + ", ".join(c.name for c in paused_cost)
            + ". Es una decisión reciente: preguntar el motivo (rendimiento o decisión del cliente).",
            {"campaigns": [c.name for c in paused_cost], "spend_share": pc_share},
        ))
    if zombies:
        out.append(Finding(
            "zombie_campaigns", "5", "estructura", "baja",
            "Hay campañas activas que no muestran anuncios.",
            "Campañas ENABLED con 0 impresiones: " + ", ".join(c.name for c in zombies)
            + ". Inflan el recuento de activas sin aportar nada.",
            {"campaigns": [c.name for c in zombies]},
        ))
    p_share = _share(len(paused), total)
    if p_share > 0.5:
        out.append(Finding(
            "paused_backlog", "5", "estructura", "info",
            "La cuenta acumula muchas campañas antiguas pausadas.",
            f"{len(paused)} de {total} campañas pausadas ({_pct(p_share)}), con {_pct(pc_share)} del gasto en pausadas "
            "con coste. Si es cero, es histórico sin borrar y no deuda real (lección del caso de cuenta gestionada).",
            {"paused": len(paused), "total": total},
        ))
    return out


# --- Paso 8: términos de búsqueda --------------------------------------------------------------

@rule
def search_terms(d: AccountData) -> list[Finding]:
    if not d.search_terms:
        return []
    out: list[Finding] = []
    visible = sum(t.cost for t in d.search_terms)
    none = [t for t in d.search_terms if t.status == "NONE"]
    none_share = _share(sum(t.cost for t in none), visible)
    if none_share >= 0.15:  # en una cuenta curada, lo que entra sin revisar es una parte pequeña
        top = sorted(none, key=lambda t: t.cost, reverse=True)[:8]
        out.append(Finding(
            "terms_uncurated", "8", "busqueda", "media",
            "Una parte importante del gasto en búsqueda entra por términos que nadie ha revisado.",
            f"{_pct(none_share)} del gasto de los términos leídos está en estado NONE (sin añadir ni excluir). "
            "Principales: " + "; ".join(f"\"{t.term}\" ({_money(t.cost, d.currency)}, {_num(t.conversions)} conv.)" for t in top)
            + ". En cuentas con conversión-proxy no se tría por conversiones: se tría por relevancia y gasto (8c). "
            "La relevancia la valora el criterio experto del informe de pago.",
            {"terms": [(t.term, t.campaign, t.cost, t.conversions) for t in top], "share_none": none_share},
        ))
    impossible = [t for t in d.search_terms if t.clicks >= 2 and t.conversions > t.clicks]
    if impossible:
        out.append(Finding(
            "terms_conv_gt_clicks", "8f", "tracking", "media",
            "Algunos términos registran más conversiones que clics, señal de un fallo de configuración.",
            "Ninguna landing convierte más de una vez por clic de forma sostenida: "
            + "; ".join(f"\"{t.term}\" {_num(t.conversions)} conv. con {t.clicks} clics" for t in impossible[:5])
            + ". Revisar el recuento y el origen de las acciones de conversión (4e).",
            {"terms": [t.term for t in impossible]},
        ))
    by_term: dict[str, set[str]] = {}
    for t in d.search_terms:
        by_term.setdefault(t.term.lower(), set()).add(t.campaign)
    dup = {k: v for k, v in by_term.items() if len(v) >= 2}
    if dup:
        dup_cost = sum(t.cost for t in d.search_terms if t.term.lower() in dup)
        out.append(Finding(
            "terms_duplicated", "8f", "estructura", "baja",
            "Las mismas búsquedas se reparten entre varias campañas, que compiten entre sí.",
            f"{_n(len(dup), 'término servido', 'términos servidos')} desde dos o más campañas ({_money(dup_cost, d.currency)}): "
            + "; ".join(f"\"{k}\" en {len(v)} campañas" for k, v in list(dup.items())[:5])
            + ". El histórico de esas búsquedas se parte y ninguna campaña aprende con el volumen completo.",
            {"terms": {k: sorted(v) for k, v in dup.items()}},
        ))
    return out


# --- Decisiones de canal ----------------------------------------------------------------------

@rule
def smart_bidding_low_volume(d: AccountData) -> list[Finding]:
    camps = [c for c in _spending(d) if c.bidding_strategy in SMART_BIDDING and c.conversions < 8 and not _is_new(c, d)]
    if not camps:
        return []
    return [Finding(
        "smart_bidding_low_volume", "canal", "gasto", "baja",
        "Hay campañas con puja automática que no tienen conversiones suficientes para que funcione bien.",
        "Puja automática con menos de 8 conversiones al mes: " + ", ".join(f"{c.name} ({c.conversions:g})" for c in camps)
        + ". Por debajo de 8 a 12 conversiones mensuales, valorar CPC manual.",
        {"campaigns": [c.name for c in camps]},
    )]


# --- Lo que no se puede ver -------------------------------------------------------------------

def not_observed(d: AccountData) -> list[NotObserved]:
    items = [
        NotObserved("4d", "Consentimiento de cookies y etiquetado de la web", "está fuera de Google Ads"),
        NotObserved("9", "Páginas de destino y analítica", "requiere GA4 o acceso a la web"),
    ]
    if any(c.channel in ("PERFORMANCE_MAX", "SHOPPING") for c in d.campaigns if c.active):
        items.append(NotObserved("8g", "Merchant Center (feed, CSS de free listings, accesos)", "requiere acceso a Merchant Center"))
    if any(c.channel == "PERFORMANCE_MAX" for c in d.campaigns if c.active):
        items.append(NotObserved("1c", "Reparto del gasto de PMax por canal", "Google no lo expone"))
    if d.conversion_actions is None:
        items.append(NotObserved("4e", "Configuración de las acciones de conversión", "no se pudieron leer"))
    if all(c.bidding_strategy is None for c in d.campaigns):
        items.append(NotObserved("1c", "Estrategia de puja por campaña", "no viene en los datos"))
    if "keywords" in d.skipped_queries:
        items.append(NotObserved("3", "Quality Score de las palabras clave", "la consulta falló"))
    if "search_terms" in d.skipped_queries:
        items.append(NotObserved("8", "Términos de búsqueda", "la consulta falló"))
    if d.search_terms_capped:
        items.append(NotObserved("8e", "Términos de búsqueda completos", "el informe viene limitado"))
    if not any(c.channel in ("SEARCH", "SHOPPING") and c.impressions > 0 for c in d.campaigns):
        items.append(NotObserved("8d", "Términos de búsqueda", "no hay campañas de búsqueda o Shopping con impresiones"))
    return items
